"""Pruebas offline de persistencia e idempotencia de la sincronización.

Cubren el criterio central de MVP-05: repetir una ejecución no duplica
oportunidades, y un fallo parcial queda visible y reanudable.

No requieren base de datos ni red: usan la implementación en memoria y un
cliente SECOP con respuestas sintéticas.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.db.repository import (
    InMemoryOpportunityRepository,
    SyncRunTracker,
    UpsertResult,
)
from app.db.sync_service import SyncRequest, SyncService
from app.secop.client import (
    PROCESSES_DATASET,
    OpportunityRecord,
    QuotaExceededError,
    SecopError,
    UpstreamUnavailableError,
)

_UNSET = object()


def make_record(
    source_id: str = "PROC-1",
    *,
    title: str = "Compra de equipos",
    status: str = "Publicado",
    published_at: datetime | None | object = _UNSET,
    raw: Mapping[str, Any] | None = None,
) -> OpportunityRecord:
    """Construye un registro sintético.

    ``published_at=None`` significa explícitamente "sin fecha". Omitir el
    parámetro usa una fecha fija, para no repetirla en cada llamada.
    """

    if published_at is _UNSET:
        published_at = datetime(2026, 9, 1, tzinfo=UTC)
    return OpportunityRecord(
        source_id=source_id,
        source_dataset=PROCESSES_DATASET,
        reference=f"REF-{source_id}",
        title=title,
        entity="EAG",
        status=status,
        modality="Contratación directa",
        published_at=published_at,  # type: ignore[arg-type]
        last_updated_at=datetime(2026, 9, 2, tzinfo=UTC),
        official_url=f"https://community.secop.gov.co/{source_id}",
        fetched_at=datetime(2026, 9, 17, tzinfo=UTC),
        raw=dict(raw or {"id_del_proceso": source_id}),
    )


class FakeSecopClient:
    """Cliente con páginas preparadas. Registra cuántas veces se consultó."""

    def __init__(self, pages: list[list[OpportunityRecord]] | Exception) -> None:
        self._pages = pages
        self.requests_made = 0
        self.offsets: list[int] = []
        self.filters: list[Mapping[str, str] | None] = []

    def iter_records(
        self,
        *,
        filters: Mapping[str, str] | None = None,
        limit: int | None = None,
        start_offset: int = 0,
    ):
        self.offsets.append(start_offset)
        self.filters.append(filters)
        if isinstance(self._pages, Exception):
            self.requests_made += 1
            raise self._pages

        emitted = 0
        for page in self._pages:
            self.requests_made += 1
            for record in page:
                if limit is not None and emitted >= limit:
                    return
                yield record
                emitted += 1


def service_with(
    client: Any, repository: InMemoryOpportunityRepository | None = None
) -> tuple[SyncService, InMemoryOpportunityRepository]:
    repo = repository or InMemoryOpportunityRepository()
    return SyncService(client=client, repository=repo), repo


# --- Idempotencia ----------------------------------------------------------


def test_first_sync_creates_records() -> None:
    client = FakeSecopClient([[make_record("A"), make_record("B")]])
    service, repo = service_with(client)

    outcome = service.run()

    assert outcome.outcome == "completed"
    assert outcome.records_created == 2
    assert repo.count() == 2


def test_repeating_the_same_sync_does_not_duplicate() -> None:
    """Criterio central de MVP-05: repetir una ejecución no duplica."""

    records = [make_record("A"), make_record("B")]
    service, repo = service_with(FakeSecopClient([records]))

    service.run()
    outcome = service.run()

    assert repo.count() == 2
    assert outcome.records_created == 0
    assert outcome.records_updated == 0
    assert outcome.records_unchanged == 2


def test_duplicates_inside_the_same_run_are_collapsed() -> None:
    """La fuente puede repetir un registro entre páginas."""

    client = FakeSecopClient([[make_record("A")], [make_record("A")]])
    service, repo = service_with(client)

    outcome = service.run()

    assert repo.count() == 1
    assert outcome.records_created == 1


def test_changed_record_is_updated_not_duplicated() -> None:
    """Un cambio real en la fuente actualiza el registro existente."""

    repo = InMemoryOpportunityRepository()
    service, _ = service_with(FakeSecopClient([[make_record("A", status="Publicado")]]), repo)
    service.run()

    changed = FakeSecopClient([[make_record("A", status="Adjudicado")]])
    service2, _ = service_with(changed, repo)
    outcome = service2.run()

    assert repo.count() == 1
    assert outcome.records_updated == 1
    stored = repo.get_by_source(PROCESSES_DATASET, "A")
    assert stored is not None
    assert stored.status == "Adjudicado"


def test_unchanged_record_refreshes_last_synced_but_keeps_first_seen() -> None:
    """``first_seen_at`` no se reescribe: registra cuándo apareció."""

    repo = InMemoryOpportunityRepository()
    service, _ = service_with(FakeSecopClient([[make_record("A")]]), repo)
    service.run()
    first = repo.get_by_source(PROCESSES_DATASET, "A")
    assert first is not None
    original_first_seen = first.first_seen_at
    original_last_synced = first.last_synced_at

    service2, _ = service_with(FakeSecopClient([[make_record("A")]]), repo)
    service2.run()
    after = repo.get_by_source(PROCESSES_DATASET, "A")
    assert after is not None

    assert after.first_seen_at == original_first_seen
    assert after.last_synced_at >= original_last_synced


def test_raw_payload_is_preserved_for_auditing() -> None:
    """La carga original permite auditar y renormalizar sin volver a la red."""

    repo = InMemoryOpportunityRepository()
    payload = {"id_del_proceso": "A", "campo_extra": "valor original"}
    service, _ = service_with(FakeSecopClient([[make_record("A", raw=payload)]]), repo)

    service.run()

    stored = repo.get_by_source(PROCESSES_DATASET, "A")
    assert stored is not None
    assert stored.raw_payload == payload


def test_different_datasets_do_not_collide() -> None:
    """La identidad incluye el conjunto de origen, no solo el identificador."""

    repo = InMemoryOpportunityRepository()
    from_other = make_record("A")
    other = OpportunityRecord(**{**from_other.__dict__, "source_dataset": "otro-dataset"})  # type: ignore[arg-type]

    repo.upsert_many([from_other, other])

    assert repo.count() == 2


# --- Fallos y reanudación --------------------------------------------------


def test_quota_failure_is_reported_not_raised() -> None:
    """Una cuota agotada debe quedar registrada, no romper la petición."""

    service, repo = service_with(FakeSecopClient(QuotaExceededError("429")))

    outcome = service.run()

    assert outcome.outcome == "failed"
    assert outcome.error_kind == "quota_exceeded"
    assert repo.count() == 0


def test_upstream_failure_is_reported() -> None:
    service, _ = service_with(FakeSecopClient(UpstreamUnavailableError("503")))

    outcome = service.run()

    assert outcome.outcome == "failed"
    assert outcome.error_kind == "UpstreamUnavailableError"


def test_partial_results_before_a_failure_are_kept() -> None:
    """Lo ya leído no se pierde si la ejecución falla en una página posterior."""

    class FailsMidway:
        requests_made = 2

        def iter_records(self, **_kwargs: Any):
            yield make_record("A")
            yield make_record("B")
            raise SecopError("fallo en la pagina siguiente")

    repo = InMemoryOpportunityRepository()
    service = SyncService(client=FailsMidway(), repository=repo)  # type: ignore[arg-type]

    outcome = service.run()

    # La ejecución sigue siendo un fallo: no se disfraza de éxito.
    assert outcome.outcome == "failed"
    # Pero el trabajo ya hecho se conserva.
    assert repo.count() == 2
    assert any("se conservaron 2" in n for n in outcome.notes)


def test_partial_failure_is_resumable_without_duplicating() -> None:
    """Repetir tras un fallo parcial no duplica lo ya guardado."""

    class FailsMidway:
        requests_made = 1

        def iter_records(self, **_kwargs: Any):
            yield make_record("A")
            raise SecopError("fallo")

    repo = InMemoryOpportunityRepository()
    SyncService(client=FailsMidway(), repository=repo).run()  # type: ignore[arg-type]
    assert repo.count() == 1

    # Segunda ejecución completa: A ya existe y no se duplica.
    service, _ = service_with(FakeSecopClient([[make_record("A"), make_record("B")]]), repo)
    outcome = service.run()

    assert repo.count() == 2
    assert outcome.records_created == 1
    assert outcome.records_unchanged == 1


def test_sync_applies_configured_filters() -> None:
    client = FakeSecopClient([[make_record("A")]])
    service, _ = service_with(client)

    service.run(SyncRequest(filters={"estado_del_procedimiento": "Publicado"}))

    assert client.filters[0] == {"estado_del_procedimiento": "Publicado"}


def test_sync_respects_limit() -> None:
    client = FakeSecopClient([[make_record(f"P-{i}") for i in range(10)]])
    service, repo = service_with(client)

    outcome = service.run(SyncRequest(limit=3))

    assert repo.count() == 3
    assert outcome.records_seen == 3


def test_clients_requests_are_reported() -> None:
    client = FakeSecopClient([[make_record("A")]])
    service, _ = service_with(client)

    outcome = service.run()

    assert outcome.requests_made == 1


# --- Listado ---------------------------------------------------------------


def test_list_recent_puts_unknown_dates_last() -> None:
    """Mostrar primero las filas sin fecha daría una lectura equivocada."""

    repo = InMemoryOpportunityRepository()
    repo.upsert_many(
        [
            make_record("sin-fecha", published_at=None),
            make_record("antigua", published_at=datetime(2026, 1, 1, tzinfo=UTC)),
            make_record("reciente", published_at=datetime(2026, 9, 1, tzinfo=UTC)),
        ]
    )

    listed = repo.list_recent(limit=10, offset=0)

    assert [o.source_id for o in listed] == ["reciente", "antigua", "sin-fecha"]


def test_list_recent_paginates() -> None:
    repo = InMemoryOpportunityRepository()
    repo.upsert_many([make_record(f"P-{i:02d}") for i in range(5)])

    page = repo.list_recent(limit=2, offset=1)

    assert len(page) == 2


# --- Resultado del upsert --------------------------------------------------


def test_upsert_result_total_sums_all_categories() -> None:
    result = UpsertResult(created=1, updated=2, unchanged=3, skipped=4)

    assert result.total == 10


# --- Ciclo de vida de la ejecución ----------------------------------------


def test_run_is_committed_before_the_network_call() -> None:
    """La ejecución se confirma antes de consultar la fuente.

    Regresión de un bloqueo real: la sincronización mantenía abierta la
    transacción durante la llamada de red, reteniendo locks sobre ``sync_runs``
    y ``sync_cursors``. Dos sincronizaciones concurrentes —o un proceso que
    moría durante la consulta— dejaban bloqueos pendientes y colgaban a las
    siguientes. Verificado contra PostgreSQL: tres sincronizaciones
    concurrentes pasaron de colgarse a completarse en menos de un segundo.
    """

    calls: list[str] = []

    class RecordingSession:
        """Sesión falsa que registra el orden de las operaciones."""

        def add(self, _obj: object) -> None:
            calls.append("add")

        def commit(self) -> None:
            calls.append("commit")

        def flush(self) -> None:  # pragma: no cover - no debería usarse
            calls.append("flush")

        def get(self, *_args: object, **_kwargs: object) -> None:
            return None

    class ClientThatRecordsOrder:
        requests_made = 0

        def iter_records(self, **_kwargs: Any):
            calls.append("network")
            yield make_record("A")

    # Se usa el constructor real para que el commit inicial ocurra.
    tracker = SyncRunTracker(
        RecordingSession(),  # type: ignore[arg-type]
        dataset=PROCESSES_DATASET,
    )
    # El constructor debe confirmar la apertura de la ejecución. Sin este
    # commit, la transacción quedaría abierta durante toda la consulta de red.
    assert calls == ["add", "commit"], f"apertura incorrecta: {calls}"
    calls.clear()

    service = SyncService(
        client=ClientThatRecordsOrder(),  # type: ignore[arg-type]
        repository=InMemoryOpportunityRepository(),
        tracker=tracker,
    )
    service.run()

    assert "network" in calls, "el cliente debió consultarse"
    # El cierre también se confirma; nada queda a medio confirmar.
    assert calls[-1] == "commit", f"el cierre no se confirmó: {calls}"
    assert "flush" not in calls, "no debe quedar una transacción a medio confirmar"

    # Y lo esencial: la apertura ya estaba confirmada antes de tocar la red,
    # que es lo que se verificó en el constructor.
    assert calls.count("commit") >= 2
