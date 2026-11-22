"""Persistencia SQL offline con SQLite; no es integración con PostgreSQL.

Cada operación usa una sesión nueva. SQLite devuelve fechas sin tzinfo incluso
con DateTime(timezone=True); estas fixtures usan UTC explícito, sin resolver la
zona horaria pendiente de SECOP. PostgreSQL usa TIMESTAMP WITH TIME ZONE.
"""

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.db.models import Base, Opportunity
from app.db.repository import SYNCED_FIELDS, SqlOpportunityRepository, UpsertResult, _has_changed
from tests.test_sync_repository import make_record


@pytest.fixture
def sqlite_engine() -> Iterator[Engine]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        Base.metadata.create_all(engine, tables=[Opportunity.__table__])
        yield engine
    finally:
        engine.dispose()


def test_sql_repeating_committed_records_in_a_new_session_is_unchanged(
    sqlite_engine: Engine,
) -> None:
    records = [make_record("A"), make_record("B")]
    with Session(sqlite_engine) as session:
        repo = SqlOpportunityRepository(session)
        assert repo.upsert_many(records) == UpsertResult(created=2)
        session.commit()
        originals = {
            item.source_id: (item.id, item.first_seen_at)
            for item in repo.list_recent(limit=10, offset=0)
        }

    with Session(sqlite_engine) as session:
        repo = SqlOpportunityRepository(session)
        assert repo.upsert_many(records) == UpsertResult(unchanged=2)
        session.commit()

    with Session(sqlite_engine) as session:
        repo = SqlOpportunityRepository(session)
        assert repo.count() == 2
        assert {
            item.source_id: (item.id, item.first_seen_at)
            for item in repo.list_recent(limit=10, offset=0)
        } == originals


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "Adjudicado"},
        {"title": "Descripción corregida"},
        {"raw": {"id_del_proceso": "A", "extra": ["cambio", {"version": 2}]}},
        {"published_at": datetime(2026, 9, 3, tzinfo=UTC)},
        {"last_updated_at": datetime(2026, 9, 4, tzinfo=UTC)},
    ],
    ids=["status", "title", "payload", "published_at", "last_updated_at"],
)
def test_sql_update_keeps_identity_and_first_seen_across_sessions(
    sqlite_engine: Engine,
    changes: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = make_record("A")
    first_seen = datetime(2026, 9, 17, tzinfo=UTC)
    monkeypatch.setattr("app.db.repository.utcnow", lambda: first_seen)
    with Session(sqlite_engine) as session:
        repo = SqlOpportunityRepository(session)
        assert repo.upsert_many([original]) == UpsertResult(created=1)
        session.commit()
        stored = repo.get_by_source(original.source_dataset, original.source_id)
        assert stored is not None
        original_id = stored.id
        stored_first_seen = stored.first_seen_at

    updated_at = datetime(2026, 9, 18, tzinfo=UTC)
    monkeypatch.setattr("app.db.repository.utcnow", lambda: updated_at)
    changed = replace(original, **changes)
    with Session(sqlite_engine) as session:
        repo = SqlOpportunityRepository(session)
        assert repo.upsert_many([changed]) == UpsertResult(updated=1)
        session.commit()

    with Session(sqlite_engine) as session:
        repo = SqlOpportunityRepository(session)
        stored = repo.get_by_source(original.source_dataset, original.source_id)
        assert stored is not None
        assert repo.count() == 1
        assert stored.id == original_id
        assert stored.first_seen_at == stored_first_seen == first_seen.replace(tzinfo=None)
        assert stored.last_synced_at == updated_at.replace(tzinfo=None)
        assert stored.status == changed.status
        assert stored.title == changed.title
        assert stored.raw_payload == changed.raw
        assert stored.published_at == changed.published_at.replace(tzinfo=None)
        assert stored.last_updated_at == changed.last_updated_at.replace(tzinfo=None)
        assert repo.upsert_many([changed]) == UpsertResult(unchanged=1)
        session.commit()


@pytest.mark.parametrize("missing_dates", [False, True])
def test_sql_preserves_source_metadata_after_commit_and_reload(
    sqlite_engine: Engine,
    missing_dates: bool,
) -> None:
    record = replace(
        make_record("A"),
        published_at=None if missing_dates else datetime(2026, 9, 1, 10, 0, 0, 123456, UTC),
        last_updated_at=None if missing_dates else datetime(2026, 9, 2, 11, 30, 0, 654321, UTC),
        raw={
            "id_del_proceso": "A",
            "fecha_original": "2026-09-01T10:00:00.123456Z",
            "urlproceso": {"url": "https://example.invalid/opportunity/A"},
            "extra": [None, {"texto": "Información sintética", "numero": 7}],
        },
    )
    with Session(sqlite_engine) as session:
        SqlOpportunityRepository(session).upsert_many([record])
        session.commit()

    with Session(sqlite_engine) as session:
        repo = SqlOpportunityRepository(session)
        stored = repo.get_by_source(record.source_dataset, record.source_id)
        assert stored is not None
        assert stored.source_id == record.source_id
        assert stored.source_dataset == record.source_dataset
        assert stored.reference == record.reference
        assert stored.official_url == record.official_url
        assert stored.raw_payload == record.raw
        for name in ("published_at", "last_updated_at"):
            incoming = getattr(record, name)
            persisted = getattr(stored, name)
            if incoming is None:
                assert persisted is None
            else:
                # Limitación de SQLite: conserva los componentes, no el offset.
                assert persisted.tzinfo is None
                assert persisted == incoming.replace(tzinfo=None)
        assert repo.upsert_many([record]) == UpsertResult(unchanged=1)
        session.commit()


def test_sql_same_identifier_in_different_sources_does_not_collide(
    sqlite_engine: Engine,
) -> None:
    first = make_record("A")
    other = replace(first, source_dataset="synthetic-source", title="Otra oportunidad")
    for record in (first, other):
        with Session(sqlite_engine) as session:
            repo = SqlOpportunityRepository(session)
            assert repo.upsert_many([record]) == UpsertResult(created=1)
            session.commit()

    with Session(sqlite_engine) as session:
        repo = SqlOpportunityRepository(session)
        assert repo.count() == 2
        stored_first = repo.get_by_source(first.source_dataset, "A")
        stored_other = repo.get_by_source(other.source_dataset, "A")
        assert stored_first is not None and stored_other is not None
        assert stored_first.id != stored_other.id
        assert stored_first.title == first.title
        assert stored_other.title == other.title
        assert repo.upsert_many([first, other]) == UpsertResult(unchanged=2)
        session.commit()


@pytest.mark.parametrize(
    ("incoming", "changed"),
    [
        (datetime(2026, 9, 1, 5, tzinfo=timezone(timedelta(hours=-5))), False),
        (datetime(2026, 9, 1, 10, tzinfo=timezone(timedelta(hours=-5))), True),
        (datetime(2026, 9, 1, 10), True),
    ],
    ids=["same-instant", "same-clock-different-instant", "naive-is-not-aware"],
)
def test_default_timestamp_comparison_preserves_timezone_semantics(
    incoming: datetime, changed: bool,
) -> None:
    """Regresión unitaria de la comparación normal; no conecta a PostgreSQL."""
    stored = Opportunity(published_at=datetime(2026, 9, 1, 10, tzinfo=UTC))
    values = {name: getattr(stored, name) for name in SYNCED_FIELDS}
    values["published_at"] = incoming

    assert _has_changed(stored, values) is changed
