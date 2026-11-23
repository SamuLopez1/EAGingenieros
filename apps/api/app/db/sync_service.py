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

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.models import SyncRun
from app.db.repository import (
    OpportunityRepository,
    SqlOpportunityRepository,
    SyncOutcome,
    SyncRunTracker,
    UpsertResult,
)
from app.secop.client import (
    PROCESSES_DATASET,
    HttpxClient,
    OpportunityRecord,
    QuotaExceededError,
    SecopClient,
    SecopError,
    deduplicate,
)

if TYPE_CHECKING:
    from app.secop.daily import DailyWindow


@dataclass
class SyncRequest:
    """Parámetros de una ejecución de sincronización."""

    limit: int | None = None
    resume: bool = False
    filters: dict[str, str] | None = None
    updated_window: DailyWindow | None = None

    def __post_init__(self) -> None:
        if self.resume and self.updated_window is not None and self.limit is not None:
            raise ValueError("Para retomar una ventana incremental, omita el límite de filas.")
        if self.resume and self.filters:
            raise ValueError("Una consulta filtrada no usa el cursor de sincronización.")


class SyncService:
    """Ejecuta la sincronización manual o programada."""

    def __init__(
        self,
        *,
        client: SecopClient,
        repository: OpportunityRepository,
        tracker: SyncRunTracker | None = None,
        dataset: str = PROCESSES_DATASET,
        session: Session | None = None,
        trigger: str = "manual",
    ) -> None:
        self._client = client
        self._repository = repository
        self._tracker = tracker
        self._tracker_supplied = tracker is not None
        self._dataset = dataset
        # Solo se usa para consultar el historial de ejecuciones. La escritura
        # de oportunidades pasa siempre por el repositorio.
        self._session = session
        self._trigger = trigger

    def _start_offset(self, request: SyncRequest) -> int:
        if not request.resume:
            return 0
        window = request.updated_window
        if window is None:
            return self._tracker.resume_offset() if self._tracker is not None else 0
        if self._session is None:
            return 0
        previous = self._session.scalars(
            select(SyncRun)
            .where(
                SyncRun.dataset == self._dataset,
                SyncRun.window_start == window.start,
                SyncRun.window_end == window.end,
                SyncRun.window_checkpoint.is_(True),
                SyncRun.id != (self._tracker.run_id if self._tracker is not None else 0),
            )
            .order_by(SyncRun.id.desc())
            .limit(1)
        ).first()
        offset = (
            previous.last_offset
            if previous is not None and previous.outcome in {"failed", "interrupted"}
            else 0
        )
        self._session.commit()
        return offset

    def run(self, request: SyncRequest | None = None) -> SyncOutcome:
        active = request or SyncRequest()
        with postgres_sync_lock(self._session, self._dataset) as available:
            if not available:
                return SyncOutcome(run_id=None, outcome="failed", error_kind="sync_in_progress")
            return self._run(active)

    def _run(self, request: SyncRequest) -> SyncOutcome:
        window = request.updated_window
        session = self._session
        if session is not None and not self._tracker_supplied:
            session.execute(
                update(SyncRun)
                .where(SyncRun.dataset == self._dataset, SyncRun.outcome == "running")
                .values(outcome="interrupted", finished_at=datetime.now(UTC))
            )
            self._tracker = SyncRunTracker(
                session, dataset=self._dataset, trigger=self._trigger,
                window_start=window.start if window else None,
                window_end=window.end if window else None,
                window_checkpoint=(
                    window is not None and not request.filters and request.limit is None
                ),
            )
        start_offset = self._start_offset(request)
        records: list[OpportunityRecord] = []
        failure: tuple[str, str] | None = None
        try:
            for record in self._client.iter_records(
                filters=request.filters,
                limit=request.limit,
                start_offset=start_offset,
                updated_window=window,
            ):
                records.append(record)
        except SecopError as error:
            kind = (
                "quota_exceeded" if isinstance(error, QuotaExceededError) else type(error).__name__
            )
            failure = (kind, str(error))

        last_offset = getattr(self._client, "next_offset", start_offset + len(records))
        try:
            result = (
                self._repository.upsert_many(deduplicate(records)) if records else UpsertResult()
            )
            advance_catalog = window is None and not request.filters and (
                failure is None or last_offset > start_offset
            )
            catalog_offset = last_offset if advance_catalog else None
            outcome = self._finish(result, last_offset, failure, catalog_offset)
            if failure is not None:
                outcome.notes.append(
                    f"se conservaron {len(records)} registros leídos antes del fallo"
                )
            return outcome
        except SQLAlchemyError:
            if session is None:
                raise
            session.rollback()
            return self._finish(
                UpsertResult(), start_offset, ("persistence_error", "No se pudo guardar el lote."),
                None,
            )

    def _finish(
        self, result: UpsertResult, last_offset: int, failure: tuple[str, str] | None,
        catalog_offset: int | None,
    ) -> SyncOutcome:
        requests_made = self._client.requests_made
        if self._tracker is not None:
            if failure is None:
                return self._tracker.succeed(
                    result, requests_made=requests_made, last_offset=last_offset,
                    catalog_offset=catalog_offset,
                )
            return self._tracker.fail(
                error_kind=failure[0], error_detail=failure[1], result=result,
                requests_made=requests_made, last_offset=last_offset, catalog_offset=catalog_offset,
            )
        return SyncOutcome(
            run_id=None,
            outcome="failed" if failure else "completed",
            records_seen=result.total,
            records_created=result.created,
            records_updated=result.updated,
            records_unchanged=result.unchanged,
            records_skipped=result.skipped,
            requests_made=requests_made,
            last_offset=last_offset,
            error_kind=failure[0] if failure else None,
            error_detail=failure[1] if failure else None,
        )

    def recent_runs(self, *, limit: int = 20) -> Sequence[SyncRun]:
        if self._session is None:
            return []
        statement = select(SyncRun).order_by(SyncRun.id.desc()).limit(limit)
        return list(self._session.scalars(statement).all())

    def close(self) -> None:
        try:
            close_client = getattr(self._client, "close", None)
            if callable(close_client):
                close_client()
        finally:
            if self._session is not None:
                self._session.close()


@contextmanager
def postgres_sync_lock(session: Session | None, dataset: str) -> Iterator[bool]:
    """Serializa la escritura del catálogo y del cursor entre API y programador."""
    if session is None or session.get_bind().dialect.name != "postgresql":
        yield True
        return
    # Conexión propia: los commits del lote no devuelven el lock al pool.
    key = {"dataset": f"eag:secop:sync:{dataset}"}
    engine = session.get_bind().engine
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        acquired = bool(connection.scalar(
            text("SELECT pg_try_advisory_lock(hashtextextended(:dataset, 0))"), key
        ))
        try:
            yield acquired
        finally:
            if acquired:
                try:
                    connection.execute(
                        text("SELECT pg_advisory_unlock(hashtextextended(:dataset, 0))"), key
                    )
                except SQLAlchemyError:
                    connection.invalidate()


def create_sync_service(
    settings: Settings, factory: sessionmaker[Session], *, trigger: str = "manual"
) -> SyncService:
    token = settings.socrata_app_token
    client = SecopClient(
        http=HttpxClient(app_token=token.get_secret_value() if token else None),
        page_size=settings.secop_page_size,
        timeout=settings.secop_timeout_seconds,
        max_retries=settings.secop_max_retries,
        max_requests=settings.secop_max_requests,
    )
    session = factory()
    return SyncService(
        client=client,
        repository=SqlOpportunityRepository(session),
        session=session,
        trigger=trigger,
    )
