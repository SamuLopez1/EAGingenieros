"""Repositorio de oportunidades y ejecuciones de sincronización.

La lógica de idempotencia vive aquí y no en el cliente SECOP, para que pueda
probarse sin red y para que el mismo criterio se aplique venga el registro de
donde venga.

Regla central: la identidad de una oportunidad es ``(source_dataset,
source_id)``. Sincronizar dos veces la misma fila oficial actualiza el registro
existente; nunca crea un duplicado.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Opportunity, SyncCursor, SyncRun, utcnow
from app.secop.client import OpportunityRecord


@dataclass
class UpsertResult:
    """Resultado de aplicar un lote. Distingue crear de actualizar y omitir."""

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0

    @property
    def total(self) -> int:
        return self.created + self.updated + self.unchanged + self.skipped


# Campos que se actualizan desde la fuente. Deliberadamente excluye
# first_seen_at, que registra cuándo apareció por primera vez y no debe
# reescribirse en cada sincronización.
SYNCED_FIELDS = (
    "reference",
    "title",
    "entity",
    "status",
    "modality",
    "published_at",
    "last_updated_at",
    "official_url",
    "raw_payload",
)


def _values_from(record: OpportunityRecord) -> dict[str, object]:
    return {
        "reference": record.reference,
        "title": record.title,
        "entity": record.entity,
        "status": record.status,
        "modality": record.modality,
        "published_at": record.published_at,
        "last_updated_at": record.last_updated_at,
        "official_url": record.official_url,
        "raw_payload": dict(record.raw),
    }


def _has_changed(
    existing: Opportunity, values: dict[str, object], *, sqlite_timestamps: bool = False
) -> bool:
    """Determina si algo relevante cambió.

    Evita escrituras y actualizaciones de marca de tiempo inútiles cuando la
    fuente devuelve la misma fila sin cambios, que es el caso habitual en una
    sincronización diaria.
    """

    for name in SYNCED_FIELDS:
        stored = getattr(existing, name)
        incoming = values[name]
        if sqlite_timestamps and isinstance(stored, datetime) and isinstance(incoming, datetime):
            # SQLite almacena componentes sin offset incluso con timezone=True.
            # Se compara su representación persistida, sin asignarle una zona.
            # PostgreSQL conserva la comparación de instantes con tzinfo.
            stored = stored.replace(tzinfo=None)
            incoming = incoming.replace(tzinfo=None)
        if stored != incoming:
            return True
    return False


class OpportunityRepository(Protocol):
    """Contrato de persistencia, para poder sustituirlo en pruebas."""

    def upsert_many(self, records: Iterable[OpportunityRecord]) -> UpsertResult: ...

    def count(self) -> int: ...

    def get_by_source(self, dataset: str, source_id: str) -> Opportunity | None: ...

    def get_by_id(self, opportunity_id: int) -> Opportunity | None: ...

    def list_recent(self, *, limit: int, offset: int) -> Sequence[Opportunity]: ...


class SqlOpportunityRepository:
    """Implementación sobre SQLAlchemy."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_many(self, records: Iterable[OpportunityRecord]) -> UpsertResult:
        result = UpsertResult()
        for record in records:
            outcome = self._upsert_one(record)
            setattr(result, outcome, getattr(result, outcome) + 1)
        self._session.flush()
        return result

    def _upsert_one(self, record: OpportunityRecord) -> str:
        values = _values_from(record)
        existing = self._session.execute(
            select(Opportunity).where(
                Opportunity.source_dataset == record.source_dataset,
                Opportunity.source_id == record.source_id,
            )
        ).scalar_one_or_none()

        now = utcnow()
        if existing is None:
            self._session.add(
                Opportunity(
                    source_dataset=record.source_dataset,
                    source_id=record.source_id,
                    first_seen_at=now,
                    last_synced_at=now,
                    **values,
                )
            )
            return "created"

        if not _has_changed(
            existing, values, sqlite_timestamps=self._session.get_bind().dialect.name == "sqlite"
        ):
            # Se refresca last_synced_at: confirma que la fuente sigue
            # devolviendo el registro, aunque su contenido no haya cambiado.
            existing.last_synced_at = now
            return "unchanged"

        for name, value in values.items():
            setattr(existing, name, value)
        existing.last_synced_at = now
        return "updated"

    def count(self) -> int:
        return self._session.execute(select(func.count()).select_from(Opportunity)).scalar_one()

    def get_by_source(self, dataset: str, source_id: str) -> Opportunity | None:
        return self._session.execute(
            select(Opportunity).where(
                Opportunity.source_dataset == dataset,
                Opportunity.source_id == source_id,
            )
        ).scalar_one_or_none()

    def get_by_id(self, opportunity_id: int) -> Opportunity | None:
        return self._session.get(Opportunity, opportunity_id)

    def list_recent(self, *, limit: int, offset: int) -> Sequence[Opportunity]:
        """Lista oportunidades de la más reciente a la más antigua.

        Las filas sin fecha de publicación se ordenan al final: mostrarlas
        primero daría la impresión de ser lo más reciente, que es justo la
        lectura equivocada.
        """

        statement = (
            select(Opportunity)
            .order_by(
                Opportunity.published_at.desc().nullslast(),
                Opportunity.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.execute(statement).scalars().all())


class InMemoryOpportunityRepository:
    """Implementación sin base de datos, para pruebas y desarrollo local.

    Reproduce el mismo comportamiento observable que la versión SQL, incluida
    la idempotencia, para que las pruebas no dependan de un motor real.
    """

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], Opportunity] = {}
        self._next_id = 1

    def upsert_many(self, records: Iterable[OpportunityRecord]) -> UpsertResult:
        result = UpsertResult()
        for record in records:
            outcome = self._upsert_one(record)
            setattr(result, outcome, getattr(result, outcome) + 1)
        return result

    def _upsert_one(self, record: OpportunityRecord) -> str:
        key = (record.source_dataset, record.source_id)
        values = _values_from(record)
        now = utcnow()
        existing = self._items.get(key)

        if existing is None:
            item = Opportunity(
                id=self._next_id,
                source_dataset=record.source_dataset,
                source_id=record.source_id,
                first_seen_at=now,
                last_synced_at=now,
                **values,
            )
            self._next_id += 1
            self._items[key] = item
            return "created"

        if not _has_changed(existing, values):
            existing.last_synced_at = now
            return "unchanged"

        for name, value in values.items():
            setattr(existing, name, value)
        existing.last_synced_at = now
        return "updated"

    def count(self) -> int:
        return len(self._items)

    def get_by_source(self, dataset: str, source_id: str) -> Opportunity | None:
        return self._items.get((dataset, source_id))

    def get_by_id(self, opportunity_id: int) -> Opportunity | None:
        for item in self._items.values():
            if item.id == opportunity_id:
                return item
        return None

    def list_recent(self, *, limit: int, offset: int) -> Sequence[Opportunity]:
        """Lista oportunidades de la más reciente a la más antigua.

        Las filas sin fecha se ordenan al final: mostrarlas primero daría la
        impresión de ser lo más reciente, que es la lectura equivocada. Por eso
        se ordena en dos grupos explícitos y solo el segundo por fecha, en vez
        de invertir una tupla que incluiría el indicador de "tiene fecha".
        """

        con_fecha = sorted(
            (o for o in self._items.values() if o.published_at is not None),
            key=lambda o: (o.published_at, o.id),
            reverse=True,
        )
        sin_fecha = sorted(
            (o for o in self._items.values() if o.published_at is None),
            key=lambda o: o.id,
            reverse=True,
        )
        return (con_fecha + sin_fecha)[offset : offset + limit]


@dataclass
class SyncOutcome:
    """Resumen de una ejecución, apto para registrar y para mostrar."""

    run_id: int | None
    outcome: str
    records_seen: int = 0
    records_created: int = 0
    records_updated: int = 0
    records_unchanged: int = 0
    records_skipped: int = 0
    requests_made: int = 0
    last_offset: int = 0
    error_kind: str | None = None
    error_detail: str | None = None
    notes: list[str] = field(default_factory=list)


class SyncRunTracker:
    """Registra el ciclo de vida de una ejecución de sincronización.

    Un fallo parcial debe quedar visible y reanudable. Por eso la ejecución se
    abre en estado ``running`` y solo pasa a ``completed`` si termina; un error
    deja ``failed`` con su tipo, sin volcar contenido sensible.
    """

    def __init__(
        self, session: Session, *, dataset: str, trigger: str = "manual",
        window_start: datetime | None = None, window_end: datetime | None = None,
        window_checkpoint: bool = False,
    ) -> None:
        self._session = session
        self._dataset = dataset
        row = SyncRun(
            dataset=dataset,
            trigger=trigger,
            window_start=window_start,
            window_end=window_end,
            window_checkpoint=window_checkpoint,
            outcome="running",
            started_at=datetime.now(UTC),
        )
        session.add(row)
        # La fila se confirma de inmediato, no solo se hace flush.
        #
        # Motivo verificado: la sincronización consulta SECOP por red entre la
        # apertura y el cierre de la ejecución. Si la transacción quedara
        # abierta durante esa espera, retendría locks sobre ``sync_runs`` y
        # ``sync_cursors``. Una segunda sincronización concurrente —o un
        # proceso que muere durante la llamada de red— dejaría bloqueos
        # pendientes y colgaría a las siguientes.
        #
        # Confirmar aquí hace que una ejecución interrumpida quede registrada
        # como ``running`` y sea visible, en lugar de desaparecer con la
        # transacción revertida.
        session.commit()
        self._run = row

    @property
    def run_id(self) -> int:
        return self._run.id

    def succeed(
        self, result: UpsertResult, *, requests_made: int, last_offset: int,
        catalog_offset: int | None = None,
    ) -> SyncOutcome:
        self._run.outcome = "completed"
        self._run.finished_at = datetime.now(UTC)
        self._run.records_seen = result.total
        self._run.records_created = result.created
        self._run.records_updated = result.updated
        self._run.records_skipped = result.skipped
        self._run.requests_made = requests_made
        self._run.last_offset = last_offset
        if catalog_offset is not None:
            self.advance_cursor(catalog_offset)
        self._session.commit()
        return SyncOutcome(
            run_id=self.run_id,
            outcome="completed",
            records_seen=result.total,
            records_created=result.created,
            records_updated=result.updated,
            records_unchanged=result.unchanged,
            records_skipped=result.skipped,
            requests_made=requests_made,
            last_offset=last_offset,
        )

    def fail(
        self,
        *,
        error_kind: str,
        error_detail: str,
        result: UpsertResult,
        requests_made: int,
        last_offset: int,
        catalog_offset: int | None = None,
    ) -> SyncOutcome:
        self._run.outcome = "failed"
        self._run.finished_at = datetime.now(UTC)
        self._run.records_seen = result.total
        self._run.records_created = result.created
        self._run.records_updated = result.updated
        self._run.records_skipped = result.skipped
        self._run.requests_made = requests_made
        self._run.last_offset = last_offset
        # Se acota el detalle: el mensaje de una excepción puede incluir la URL
        # consultada y no debe crecer sin límite en la base de datos.
        self._run.error_kind = error_kind[:64]
        self._run.error_detail = error_detail[:500]
        if catalog_offset is not None:
            self.advance_cursor(catalog_offset)
        self._session.commit()
        return SyncOutcome(
            run_id=self.run_id,
            outcome="failed",
            records_seen=result.total,
            records_created=result.created,
            records_updated=result.updated,
            records_unchanged=result.unchanged,
            records_skipped=result.skipped,
            requests_made=requests_made,
            last_offset=last_offset,
            error_kind=error_kind,
            error_detail=error_detail[:500],
        )

    def cursor(self) -> SyncCursor:
        """Devuelve o crea el cursor de este conjunto."""

        found = self._session.get(SyncCursor, self._dataset)
        if found is None:
            found = SyncCursor(dataset=self._dataset, last_offset=0)
            self._session.add(found)
        return found

    def resume_offset(self) -> int:
        """Lee el cursor sin retener una transacción durante la llamada de red."""

        offset = self.cursor().last_offset
        self._session.commit()
        return offset

    def advance_cursor(self, offset: int) -> None:
        cursor = self.cursor()
        cursor.last_offset = offset
        cursor.last_run_id = self.run_id
