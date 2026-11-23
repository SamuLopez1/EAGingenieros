"""Smoke opt-in sobre SECOP II público y SQLite desechable, sin guardar filas."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.contracts import OpportunitySummary
from app.db.models import Base
from app.db.repository import SqlOpportunityRepository, SyncOutcome
from app.db.sync_service import SyncRequest, SyncService
from app.secop.client import (
    PROCESSES_DATASET,
    RECEPTION_FIELD,
    SOCRATA_ROOT,
    SecopClient,
    SecopError,
)
from app.secop.daily import plan_daily_window

ENDPOINT = f"{SOCRATA_ROOT}/resource/{PROCESSES_DATASET}.json"
SELECT = (
    "id_del_proceso,estado_del_procedimiento,fecha_de_publicacion_del,"
    f"fecha_de_ultima_publicaci,{RECEPTION_FIELD},urlproceso"
)
TIMEOUT = 12.0


class PublicSample:
    def __init__(self, http: httpx.Client) -> None:
        self._http = http
        self.count = 0

    def get(self, url: str, *, params: Mapping[str, Any], timeout: float) -> httpx.Response:
        if url != ENDPOINT or self.count >= 5 or not 1 <= int(params["$limit"]) <= 5:
            raise ValueError("La consulta excede el alcance del smoke")
        self.count += 1
        try:
            response = self._http.get(url, params={**params, "$select": SELECT}, timeout=timeout)
        except httpx.HTTPError as error:
            report(request=self.count, transport=type(error).__name__)
            raise
        report(request=self.count, http=response.status_code)
        return response


def report(**values: object) -> None:
    print(json.dumps(values), flush=True)


def literal(value: datetime) -> str:
    return value.astimezone(UTC).replace(tzinfo=None).isoformat(timespec="milliseconds")


def run(sample: PublicSample, as_of: datetime) -> int:
    window = plan_daily_window(as_of)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    report(window_start=literal(window.start), window_end=literal(window.end))

    def client() -> SecopClient:
        return SecopClient(
            http=sample, timeout=TIMEOUT, page_size=5, max_retries=0, max_requests=1
        )

    def sync(request: SyncRequest, stage: str) -> SyncOutcome:
        with Session(engine, expire_on_commit=False) as session:
            outcome = SyncService(
                client=client(), repository=SqlOpportunityRepository(session), session=session,
            ).run(request)
        report(
            stage=stage, outcome=outcome.outcome, seen=outcome.records_seen,
            created=outcome.records_created, updated=outcome.records_updated,
            unchanged=outcome.records_unchanged, error=outcome.error_kind,
        )
        return outcome

    try:
        Base.metadata.create_all(engine)
        old_created = 0
        try:
            old = sample.get(
                ENDPOINT,
                params={
                    "$limit": 5,
                    "$where": (
                        "estado_del_procedimiento = 'Publicado' AND "
                        f"fecha_de_publicacion_del < '{literal(window.start)}' AND "
                        f"{RECEPTION_FIELD} > '{literal(as_of)}' AND id_del_proceso IS NOT NULL"
                    ),
                },
                timeout=TIMEOUT,
            )
            old.raise_for_status()
            candidates = old.json()
            report(older_published_with_future_reception=len(candidates))
            if candidates:
                result = sync(
                    SyncRequest(
                        filters={"id_del_proceso": candidates[0]["id_del_proceso"]}, limit=1,
                    ),
                    "initial_old_sample",
                )
                old_created = result.records_created
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as error:
            report(stage="older_candidates", error=type(error).__name__)

        recent = client().fetch_page(page_size=3, order=None, updated_window=window)
        report(incremental_candidates=len(recent.records))
        if not recent.records:
            return 2
        entry = recent.records[0]
        if entry.last_updated_at is None or not window.start <= entry.last_updated_at < window.end:
            report(stage="incremental_sample", error="outside_window")
            return 2
        request = SyncRequest(
            filters={"id_del_proceso": entry.source_id}, updated_window=window, limit=1,
        )
        first = sync(request, "incremental_first")
        repeat = sync(request, "incremental_repeat")
        with Session(engine) as session:
            repo = SqlOpportunityRepository(session)
            rows = [OpportunitySummary.model_validate(row) for row in repo.list_recent(
                limit=5, offset=0
            )]
        report(
            persisted_unique=len(rows),
            with_official_status=sum(row.status is not None for row in rows),
            with_reception=sum(row.reception_at is not None for row in rows),
            with_last_sync=sum(row.last_synced_at is not None for row in rows),
            requests=sample.count,
        )
        idempotent = (
            first.outcome == repeat.outcome == "completed"
            and first.records_seen == repeat.records_seen == 1
            and repeat.records_created == 0
            and len(rows) == old_created + first.records_created
        )
        return 0 if idempotent else 2
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True)
    parser.add_argument("--as-of", help="Instante ISO 8601 con offset")
    args = parser.parse_args()
    try:
        as_of = datetime.fromisoformat(args.as_of) if args.as_of else datetime.now(UTC)
        with httpx.Client(follow_redirects=False, trust_env=False) as http:
            return run(PublicSample(http), as_of)
    except (ValueError, SecopError) as error:
        report(error=type(error).__name__)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
