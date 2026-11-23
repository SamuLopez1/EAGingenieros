"""Recuperación y rollback reales sobre PostgreSQL local, con datos de fixture."""

import json
import os
import re
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.auth import AuthServices
from app.config import Settings
from app.db.margin_models import MarginVersion
from app.db.repository import SqlOpportunityRepository
from app.db.staffing_models import StaffingCorrection
from app.main import create_app
from tests.test_dossier import ANALYST, Memberships, Scanner, Validator, api
from tests.test_postgres_sync_integration import OWNER_LABEL
from tests.test_postgres_sync_integration import postgres_engine as postgres_engine
from tests.test_postgres_sync_integration import pytestmark as pytestmark
from tests.test_reports import ROOT, prepare_case
from tests.test_retention import ENVIRONMENT, KEY, counts, set_boundary
from tests.test_sync_repository import make_record

BASE_REVISION = "20261122000012"
RETENTION_REVISION = "20261122000011"


def docker(*args: str) -> str:
    result = subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, f"Falló Docker {args[0]} en PostgreSQL desechable"
    return result.stdout.strip()


def retention(action: str, url: str, ledger: Path) -> dict[str, int]:
    env = {
        **os.environ,
        "EAG_DATABASE_URL": url,
        "EAG_RETENTION_LEDGER_ID": str(ENVIRONMENT),
        "EAG_RETENTION_LEDGER_SECRET": KEY.decode(),
    }
    result = subprocess.run(
        [sys.executable, "-m", "app.operations.retention", action, "--ledger", str(ledger)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, f"Falló el comando de retención {action}"
    return json.loads(result.stdout)["counts"]


def fixture_app(url: str):
    settings = Settings(
        _env_file=None,
        database_url=SecretStr(url),
        document_download_secret=SecretStr("fixture-only-for-this-run-123456789"),
    )
    app = create_app(settings, auth_services=AuthServices(Validator(), Memberships()))
    app.state.document_services = replace(app.state.document_services, scanner=Scanner())
    return app, settings


def test_backup_restore_replays_purges_and_rehearses_rollback(
    postgres_engine,
    tmp_path,
    monkeypatch,
) -> None:
    config = Config("alembic.ini")
    with postgres_engine.begin() as connection:
        for role in ("anon", "authenticated"):
            connection.execute(text(f"CREATE ROLE {role} NOLOGIN"))
            connection.execute(
                text(
                    f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {role}",
                )
            )
    command.upgrade(config, RETENTION_REVISION)
    with postgres_engine.begin() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT relrowsecurity FROM pg_class "
                    "WHERE oid = 'retention_tombstones'::regclass",
                )
            )
            is True
        )
        for role in ("anon", "authenticated"):
            assert (
                connection.scalar(
                    text(
                        "SELECT has_table_privilege(:role, 'retention_tombstones', "
                        "'SELECT, INSERT, DELETE')",
                    ),
                    {"role": role},
                )
                is False
            )
        SqlOpportunityRepository(Session(bind=connection)).upsert_many(
            [
                make_record("RESTORE-A"),
                make_record("RESTORE-B"),
            ]
        )

    source_url = postgres_engine.url
    database = source_url.database
    assert source_url.host == "127.0.0.1" and database
    token = re.fullmatch(r"mvp05_([0-9a-f]{32})", database)
    assert token is not None
    suffix = token.group(1)
    container = f"eag-mvp05-test-{suffix}"
    assert (
        docker("inspect", "--format", f'{{{{index .Config.Labels "{OWNER_LABEL}"}}}}', container)
        == suffix
    )
    app, settings = fixture_app(source_url.render_as_string(hide_password=False))
    with TestClient(app) as client:
        _, _, _, _, approval = prepare_case((client, app, settings, postgres_engine))
    boundary = datetime.now(UTC) - timedelta(seconds=2)
    set_boundary(postgres_engine, approval["revision"], boundary)
    organization = settings.initial_organization_id
    with Session(postgres_engine) as db, db.begin():
        db.add(MarginVersion(
            organization_id=organization, opportunity_id=1, scenario_id=UUID(int=91),
            version=1, actor_id=UUID(int=1), updated_at=boundary, event="edicion",
            inputs={}, basis={}, calculation={}, rules_version="fixture", expires_at=boundary,
        ))
        db.add(StaffingCorrection(
            organization_id=organization, opportunity_id=1, fingerprint="a" * 64,
            sequence=1, comparison_revision=approval["revision"], row_id="b" * 64,
            actor_id=UUID(int=1), reason="Prueba sintética", created_at=boundary,
            previous={}, corrected={},
        ))

    def derived_counts(engine):
        with engine.connect() as connection:
            return connection.execute(text(
                "SELECT (SELECT count(*) FROM margin_versions), "
                "(SELECT count(*) FROM staffing_corrections)"
            )).one()

    assert derived_counts(postgres_engine) == (1, 1)
    assert counts(postgres_engine) == (1, 1, 1, 2, 1, 1, 1, 2)

    dump = "/tmp/eag-mvp13-fixture.dump"
    docker("exec", container, "pg_dump", "-Fc", "-U", "mvp05_test", "-f", dump, database)
    ledger = tmp_path / "current-private-ledger.json"
    live_dsn = source_url.render_as_string(hide_password=False)
    before_purge = retention("dry-run", live_dsn, ledger)
    assert (
        before_purge["documentos_vencidos"],
        before_purge["comparaciones_vencidas"],
        before_purge["envios_vencidos"],
    ) == (1, 2, 1)
    assert before_purge["margenes_vencidos"] == 1
    assert retention("purge", live_dsn, ledger) == {
        "comparison": 2,
        "delivery": 1,
        "document": 1,
        "margin": 1,
    }
    cleared = (0, 0, 0, 0, 0, 1, 1, 2)
    assert counts(postgres_engine) == cleared
    assert derived_counts(postgres_engine) == (0, 0)
    print("Purga PostgreSQL: expediente/OCR, 2 revisiones y 1 envío; maestros preservados.")

    recovery = f"restore_{suffix}"
    docker("exec", container, "createdb", "-U", "mvp05_test", recovery)
    docker(
        "exec",
        container,
        "pg_restore",
        "--exit-on-error",
        "--no-owner",
        "-U",
        "mvp05_test",
        "-d",
        recovery,
        dump,
    )
    restored_url = source_url.set(database=recovery)
    restored = create_engine(restored_url, echo=False)
    try:
        assert counts(restored) == (1, 1, 1, 2, 1, 1, 1, 2)
        assert derived_counts(restored) == (1, 1)
        shadow_dsn = restored_url.render_as_string(hide_password=False)
        assert retention("replay", shadow_dsn, ledger) == {
            "comparison": 2,
            "delivery": 1,
            "document": 1,
            "margin": 1,
        }
        assert counts(restored) == cleared
        assert derived_counts(restored) == (0, 0)
        print("pg_dump/pg_restore: backup anterior; reaplicación elimina contenido restaurado.")

        with monkeypatch.context() as target:
            target.setenv("EAG_DATABASE_URL", restored_url.render_as_string(hide_password=False))
            command.downgrade(config, BASE_REVISION)
            assert "retention_tombstones" not in inspect(restored).get_table_names()
            with restored.connect() as connection:
                assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                    BASE_REVISION
                )
            assert counts(restored) == cleared
            command.upgrade(config, RETENTION_REVISION)
        assert retention("replay", shadow_dsn, ledger) == {}
        assert retention("replay", shadow_dsn, ledger) == {}
        recovered_app, _ = fixture_app(restored_url.render_as_string(hide_password=False))
        with TestClient(recovered_app) as client:
            assert client.get(api(1), headers=ANALYST).json()["documents"] == []
            assert client.get(f"{ROOT}/{approval['revision']}", headers=ANALYST).status_code == 409
        assert counts(restored) == cleared
        print("Rollback .000011 -> .000012 -> .000011 y reaplicación idempotente verificados.")
    finally:
        restored.dispose()
