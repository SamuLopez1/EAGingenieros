"""Servicio de sincronización de oportunidades desde SECOP II.

Orquesta el cliente y el repositorio. Su responsabilidad es que una ejecución
sea idempotente, observable y reanudable: repetirla no duplica nada, un fallo
parcial queda registrado y el avance se conserva para continuar.

Lo que este servicio NO hace, deliberadamente:

- No obtiene documentos. La relación entre el conjunto de procesos y el de
  archivos no está confirmada, así que el expediente se completa por carga
  manual (issue MVP-07).
- No interpreta ni compara requisitos. Eso corresponde al análisis posterior.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SyncRun
from app.db.repository import (
    OpportunityRepository,
    SyncOutcome,
    SyncRunTracker,
    UpsertResult,
)
from app.secop.client import (
    OpportunityRecord,
    QuotaExceededError,
    SecopClient,
    SecopError,
    deduplicate,
)
from app.secop.sources import Source


@dataclass
class SyncRequest:
    """Parámetros de una ejecución de sincronización."""

    limit: int | None = None
    page_size: int = 100
    resume: bool = False
    filters: dict[str, str] | None = None


class SyncService:
    """Ejecuta la sincronización manual o programada de una fuente."""

    def __init__(
        self,
        *,
        client: SecopClient,
        repository: OpportunityRepository,
        tracker: SyncRunTracker | None = None,
        dataset: str | None = None,
        session: Session | None = None,
    ) -> None:
        self._client = client
        self._repository = repository
        self._tracker = tracker
        # El conjunto se toma del cliente, que a su vez lo toma del registro de
        # fuentes. Antes llegaba como parámetro independiente y podía divergir:
        # se habría registrado la ejecución bajo un conjunto mientras las filas
        # se escribían desde otro, y el cursor de reanudación habría avanzado
        # sobre la fuente equivocada.
        self._source = client.source
        if dataset is not None and dataset != self._source.dataset:
            raise ValueError(
                f"el conjunto {dataset!r} no coincide con el del cliente "
                f"({self._source.dataset!r}); la ejecución se registraría bajo "
                "una fuente distinta de la que produce las filas"
            )
        self._dataset = self._source.dataset
        # Solo se usa para consultar el historial de ejecuciones. La escritura
        # de oportunidades pasa siempre por el repositorio.
        self._session = session

    @property
    def source(self) -> Source:
        return self._source

    @property
    def dataset(self) -> str:
        return self._dataset

    def _start_offset(self, request: SyncRequest) -> int:
        if not request.resume or self._tracker is None:
            return 0
        return self._tracker.cursor().last_offset

    def run(self, request: SyncRequest | None = None) -> SyncOutcome:
        """Ejecuta una sincronización completa y devuelve su resultado.

        Los errores del cliente no se propagan sin registro: se convierten en
        un resultado fallido para que la ejecución quede visible y el panel no
        muestre un éxito falso.
        """

        active = request or SyncRequest()
        start_offset = self._start_offset(active)

        # Se acumula lo leído a medida que llega. Si la iteración falla en una
        # página intermedia, lo ya obtenido se persiste en lugar de perderse:
        # una sincronización diaria que falla a mitad no debe descartar todo lo
        # anterior y volver a empezar.
        records: list[OpportunityRecord] = []
        try:
            for record in self._client.iter_records(
                filters=active.filters,
                limit=active.limit,
                start_offset=start_offset,
            ):
                records.append(record)
        except QuotaExceededError as error:
            return self._persist_partial(records, start_offset, "quota_exceeded", str(error))
        except SecopError as error:
            return self._persist_partial(records, start_offset, type(error).__name__, str(error))

        # La fuente puede repetir un registro entre páginas si se publica
        # mientras se recorre. Se conserva la última versión vista.
        unique = deduplicate(records)
        result = self._repository.upsert_many(unique)

        last_offset = start_offset + len(records)
        if self._tracker is not None:
            outcome = self._tracker.succeed(
                result,
                requests_made=self._client.requests_made,
                last_offset=last_offset,
            )
            if outcome.outcome == "completed":
                self._tracker.advance_cursor(last_offset)
            return outcome

        return SyncOutcome(
            run_id=None,
            outcome="completed",
            records_seen=result.total,
            records_created=result.created,
            records_updated=result.updated,
            records_unchanged=result.unchanged,
            requests_made=self._client.requests_made,
            last_offset=last_offset,
        )

    def _persist_partial(
        self,
        records: list[OpportunityRecord],
        start_offset: int,
        kind: str,
        detail: str,
    ) -> SyncOutcome:
        """Guarda lo leído antes del fallo y registra la ejecución como fallida.

        El resultado sigue siendo ``failed``: guardar lo parcial no convierte la
        ejecución en exitosa. La diferencia es que el trabajo ya hecho no se
        pierde y la siguiente ejecución lo reconoce como existente.
        """

        if records:
            self._repository.upsert_many(deduplicate(records))

        outcome = self._record_failure(kind, detail)
        outcome.notes.append(
            f"se conservaron {len(records)} registros leídos antes del fallo"
        )
        if records:
            outcome.last_offset = start_offset + len(records)
        return outcome

    def _record_failure(self, kind: str, detail: str) -> SyncOutcome:
        if self._tracker is not None:
            return self._tracker.fail(error_kind=kind, error_detail=detail)
        return SyncOutcome(
            run_id=None,
            outcome="failed",
            requests_made=self._client.requests_made,
            error_kind=kind,
            error_detail=detail,
        )

    def recent_runs(self, *, limit: int = 20) -> Sequence[SyncRun]:
        """Historial reciente de ejecuciones, del más nuevo al más antiguo."""

        if self._session is None:
            return []
        statement = select(SyncRun).order_by(SyncRun.id.desc()).limit(limit)
        return list(self._session.execute(statement).scalars().all())

    def empty_result(self) -> UpsertResult:
        """Resultado vacío, útil para respuestas sin cambios."""

        return UpsertResult()
