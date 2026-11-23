"""Planifica o ejecuta una sincronización incremental de SECOP II."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")
DAILY_CUTOVER = time(hour=6)
LOOKBACK_DAYS = 7


@dataclass(frozen=True)
class DailyWindow:
    """Ventana candidata [start, end) y próximo corte, en hora Colombia."""

    start: datetime
    end: datetime
    next_run: datetime

    def __post_init__(self) -> None:
        if self.start.utcoffset() is None or self.end.utcoffset() is None:
            raise ValueError("Los límites de la ventana deben incluir zona u offset")
        if self.start >= self.end:
            raise ValueError("El inicio de la ventana debe ser anterior al fin")


def plan_daily_window(now: datetime) -> DailyWindow:
    """Ancla la ventana al último corte de las 06:00, no a la hora del proceso."""
    if now.utcoffset() is None:
        raise ValueError("La fecha de referencia debe incluir zona u offset")
    local = now.astimezone(BOGOTA)
    end = datetime.combine(local.date(), DAILY_CUTOVER, BOGOTA)
    if local < end:
        end -= timedelta(days=1)
    return DailyWindow(
        start=end - timedelta(days=LOOKBACK_DAYS),
        end=end,
        next_run=end + timedelta(days=1),
    )


def run_daily(plan: DailyWindow) -> int:
    from sqlalchemy.exc import SQLAlchemyError

    from app.config import Settings
    from app.db.session import create_engine_from_url, create_session_factory
    from app.db.sync_service import SyncRequest, create_sync_service

    try:
        settings = Settings()
        engine = create_engine_from_url(settings.require_database_url())
    except (ValueError, RuntimeError, SQLAlchemyError):
        print(json.dumps({"outcome": "failed", "error_kind": "database_configuration"}))
        return 1

    try:
        service = create_sync_service(settings, create_session_factory(engine), trigger="daily")
        try:
            outcome = service.run(SyncRequest(resume=True, updated_window=plan))
        finally:
            service.close()
    except SQLAlchemyError:
        print(json.dumps({"outcome": "failed", "error_kind": "database_unavailable"}))
        return 1
    finally:
        engine.dispose()

    print(json.dumps({
        "outcome": outcome.outcome,
        "run_id": outcome.run_id,
        "records_seen": outcome.records_seen,
        "records_created": outcome.records_created,
        "records_updated": outcome.records_updated,
        "records_unchanged": outcome.records_unchanged,
        "requests_made": outcome.requests_made,
        "last_offset": outcome.last_offset,
        "error_kind": outcome.error_kind,
        "window_start": plan.start.astimezone(UTC).isoformat(),
        "window_end": plan.end.astimezone(UTC).isoformat(),
    }))
    return 0 if outcome.outcome == "completed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", help="Instante ISO 8601 con offset; por defecto, ahora")
    parser.add_argument("--run", action="store_true", help="Escribe en PostgreSQL y consulta SECOP")
    args = parser.parse_args()
    try:
        plan = plan_daily_window(
            datetime.fromisoformat(args.as_of) if args.as_of else datetime.now(UTC)
        )
    except ValueError as exc:
        parser.error(str(exc))
    if args.run:
        return run_daily(plan)
    print(
        json.dumps(
            {
                "mode": "plan_only",
                "timezone": BOGOTA.key,
                "window_start_utc_inclusive": plan.start.astimezone(UTC).isoformat(),
                "window_end_utc_exclusive": plan.end.astimezone(UTC).isoformat(),
                "cutover_colombia": plan.end.isoformat(),
                "next_cutover_colombia": plan.next_run.isoformat(),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
