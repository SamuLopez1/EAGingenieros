r"""Integración opt-in: PostgreSQL real, SECOP simulado y datos sintéticos.

Desde apps/api, con Docker accesible y la imagen local postgres:17.6-bookworm:
  $env:EAG_TEST_POSTGRES = '1'
  .\.venv\Scripts\python.exe -m pytest -v -s tests/test_postgres_sync_integration.py
  Remove-Item Env:EAG_TEST_POSTGRES

No acepta una URL externa ni lee .env. Crea su propio contenedor y base únicos,
sin descargar imágenes, aplica las migraciones de MVP-05 y retira su contenedor.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import time
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import URL, Engine, create_engine, inspect, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Opportunity, SyncCursor, SyncRun
from app.db.repository import SqlOpportunityRepository, SyncOutcome, UpsertResult
from app.db.sync_service import SyncRequest, SyncService, postgres_sync_lock
from app.secop.client import PROCESSES_DATASET, SecopClient, normalise_record
from app.secop.daily import plan_daily_window, run_daily
from tests.test_secop_client import FakeHttp, FakeResponse, row
from tests.test_sync_repository import assert_initial_and_incremental_catalog

pytestmark = pytest.mark.skipif(
    os.environ.get("EAG_TEST_POSTGRES") != "1",
    reason="opt-in: EAG_TEST_POSTGRES=1; requiere Docker e imagen PostgreSQL local",
)

REVISION = "20261122000002"
IMAGE = "postgres:17.6-bookworm"
OWNER_LABEL = "eag.mvp05-test"


@pytest.fixture
def postgres_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    docker = shutil.which("docker")
    if docker is None:
        pytest.fail("Docker no está instalado; no se ejecutó integración PostgreSQL")
    token = uuid4().hex
    container = f"eag-mvp05-test-{token}"
    database = f"mvp05_{token}"

    def cli(*args: str, timeout: int = 15) -> str:
        result = subprocess.run(
            [docker, *args], capture_output=True, text=True, timeout=timeout, check=False,
        )
        if result.returncode:
            # No se vuelcan argumentos ni entorno, que incluyen la clave efímera.
            raise RuntimeError(f"Docker {args[0]} falló; comprobar motor e imagen local {IMAGE}")
        return result.stdout.strip()

    engine = None
    try:
        password = secrets.token_hex(24)
        cli(
            "run", "--detach", "--pull=never", "--name", container,
            "--label", f"{OWNER_LABEL}={token}",
            "--publish", "127.0.0.1::5432",
            "--env", f"POSTGRES_DB={database}",
            "--env", "POSTGRES_USER=mvp05_test",
            "--env", f"POSTGRES_PASSWORD={password}",
            "--tmpfs", "/var/lib/postgresql/data:rw",
            IMAGE, timeout=30,
        )
        print(f"PostgreSQL desechable: {container}; base: {database}", flush=True)
        address = cli("port", container, "5432/tcp")
        host, port = address.rsplit(":", 1)
        assert host == "127.0.0.1" and port.isdigit()
        url = URL.create(
            "postgresql+psycopg", username="mvp05_test", password=password,
            host=host, port=int(port), database=database,
            query={
                "connect_timeout": "3",
                "options": "-c statement_timeout=5000 -c lock_timeout=3000",
            },
        )
        # Ignora cualquier configuración real, tanto variables como archivos.
        for key in tuple(os.environ):
            if key.startswith("EAG_"):
                monkeypatch.delenv(key)
        monkeypatch.setitem(Settings.model_config, "env_file", None)
        monkeypatch.setenv("EAG_DATABASE_URL", url.render_as_string(hide_password=False))
        engine = create_engine(url, pool_pre_ping=True, echo=False)
        deadline = time.monotonic() + 45
        while True:
            try:
                with engine.connect() as connection:
                    assert connection.scalar(text("SELECT 1")) == 1
                break
            except OperationalError:
                if time.monotonic() >= deadline:
                    pytest.fail("PostgreSQL desechable no aceptó conexiones en 45 segundos")
                time.sleep(0.25)
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        command.upgrade(config, REVISION)
        assert set(inspect(engine).get_table_names()) == {
            "alembic_version", "opportunities", "sync_runs", "sync_cursors",
            "saved_opportunity_filters",
        }
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == REVISION
            assert connection.scalar(text("SELECT current_database()")) == database
            version = connection.scalar(text("SHOW server_version"))
            print(f"Servidor real: {version}; revisión {REVISION}")
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        # Inspecciona solo el nombre único creado aquí y exige la etiqueta propia.
        ownership = subprocess.run(
            [docker, "inspect", "--format", f'{{{{ index .Config.Labels "{OWNER_LABEL}" }}}}',
             container], capture_output=True, text=True, timeout=10, check=False,
        )
        if ownership.returncode == 0:
            assert ownership.stdout.strip() == token, "no se elimina un recurso ajeno"
            cli("rm", "--force", "--volumes", container)
            print(f"Retirado: {container} (incluidos sus volúmenes anónimos)")


def synchronize(engine: Engine, http: FakeHttp, *, resume: bool = False) -> SyncOutcome:
    """Cada ejecución abre y cierra una sesión; el HTTP nunca hace red."""
    with Session(engine, expire_on_commit=False) as session:
        service = SyncService(
            client=SecopClient(http=http, page_size=2),
            repository=SqlOpportunityRepository(session), session=session,
        )
        return service.run(SyncRequest(resume=resume))


def test_initial_and_incremental_catalog_with_postgres(postgres_engine: Engine) -> None:
    assert_initial_and_incremental_catalog(postgres_engine)


def test_mvp05_migration_idempotence_and_recovery(postgres_engine: Engine) -> None:
    engine = postgres_engine
    a = row(
        id_del_proceso="SYNTHETIC-A",
        fecha_de_publicacion_del="2026-09-01T10:00:00.123456Z",
        fecha_de_ultima_publicaci="2026-09-02T11:30:00.654321Z",
        urlproceso={"url": "https://example.invalid/opportunities/A"},
        extra={"sintetico": True, "version": 1},
    )
    b = row(id_del_proceso="SYNTHETIC-B")

    def complete_http() -> FakeHttp:
        return FakeHttp([FakeResponse([a, b]), FakeResponse([])])

    first = synchronize(engine, complete_http())
    assert first.outcome == "completed"
    assert (first.records_seen, first.records_created, first.records_updated) == (2, 2, 0)
    with Session(engine) as session:
        repo = SqlOpportunityRepository(session)
        stored = repo.get_by_source(PROCESSES_DATASET, "SYNTHETIC-A")
        assert stored is not None
        original_id, original_first_seen = stored.id, stored.first_seen_at
        assert stored.published_at == datetime(2026, 9, 1, 10, 0, 0, 123456, UTC)
        assert stored.last_updated_at == datetime(2026, 9, 2, 11, 30, 0, 654321, UTC)
        assert stored.official_url == a["urlproceso"]["url"]
        assert stored.raw_payload == a
        assert repo.count() == 2
    print("1. Primera sincronización: vistos=2, creados=2, actualizados=0")

    second = synchronize(engine, complete_http())
    assert second.outcome == "completed"
    assert (second.records_created, second.records_updated, second.records_unchanged) == (0, 0, 2)
    print("2. Repetición: creados=0, actualizados=0, sin_cambios=2")

    a = {**a, "estado_del_procedimiento": "Adjudicado", "extra": {"version": 2}}
    changed = synchronize(engine, complete_http())
    assert (
        changed.records_created, changed.records_updated, changed.records_unchanged,
    ) == (0, 1, 1)
    with Session(engine) as session:
        repo = SqlOpportunityRepository(session)
        stored = repo.get_by_source(PROCESSES_DATASET, "SYNTHETIC-A")
        assert stored is not None
        assert (stored.id, stored.first_seen_at) == (original_id, original_first_seen)
        assert stored.status == "Adjudicado" and stored.raw_payload == a
        assert repo.count() == 2
    print("3. Cambio: actualizados=1; ID y first_seen_at conservados")

    # La carga original permanece igual: cambiar su texto sería un cambio real
    # de raw_payload, aunque dos fechas normalizadas representen el mismo instante.
    record = normalise_record(a, fetched_at=datetime(2026, 9, 17, tzinfo=UTC))
    assert record is not None and record.published_at and record.last_updated_at
    equivalent = replace(
        record,
        published_at=record.published_at.astimezone(timezone(timedelta(hours=-5))),
        last_updated_at=record.last_updated_at.astimezone(timezone(timedelta(hours=3))),
    )
    with Session(engine) as session:
        session.execute(text("SET TIME ZONE 'Etc/GMT-3'"))
        repo = SqlOpportunityRepository(session)
        stored = repo.get_by_source(PROCESSES_DATASET, "SYNTHETIC-A")
        assert stored is not None and stored.published_at is not None
        assert stored.published_at.utcoffset() == timedelta(hours=3)
        assert stored.published_at == equivalent.published_at
        assert repo.upsert_many([equivalent]) == UpsertResult(unchanged=1)
        session.commit()
    print("4. Offsets -05:00/+03:00: instantes equivalentes, actualizados=0")

    c = row(id_del_proceso="SYNTHETIC-C")
    partial = synchronize(
        engine, FakeHttp([FakeResponse([a, c]), FakeResponse({}, status_code=429)]),
    )
    assert partial.outcome == "failed" and partial.error_kind == "quota_exceeded"
    assert (partial.records_seen, partial.records_created, partial.records_updated) == (2, 1, 0)
    assert (partial.records_unchanged, partial.requests_made, partial.last_offset) == (1, 2, 2)
    with Session(engine) as session:
        failed = session.get(SyncRun, partial.run_id)
        cursor = session.get(SyncCursor, PROCESSES_DATASET)
        assert failed is not None and cursor is not None
        assert failed.outcome == "failed" and failed.error_kind == "quota_exceeded"
        assert (failed.records_seen, failed.records_created, failed.records_updated) == (2, 1, 0)
        assert (failed.records_skipped, failed.requests_made, failed.last_offset) == (0, 2, 2)
        assert failed.finished_at is not None
        assert (cursor.last_offset, cursor.last_run_id) == (2, partial.run_id)
        repo = SqlOpportunityRepository(session)
        stored_c = repo.get_by_source(PROCESSES_DATASET, "SYNTHETIC-C")
        assert stored_c is not None and repo.count() == 3
        c_id = stored_c.id
    print("5. 429 simulado: fallo visible, creados=1, sin_cambios=1, cursor=2 persistido")

    d = row(id_del_proceso="SYNTHETIC-D")
    resumed_http = FakeHttp([FakeResponse([c, d]), FakeResponse([])])
    resumed = synchronize(engine, resumed_http, resume=True)
    assert resumed_http.calls[0]["params"]["$offset"] == 2
    assert resumed.outcome == "completed"
    assert (
        resumed.records_created, resumed.records_updated, resumed.records_unchanged,
    ) == (1, 0, 1)
    assert (resumed.requests_made, resumed.last_offset) == (2, 4)
    with Session(engine) as session:
        repo = SqlOpportunityRepository(session)
        assert repo.count() == 4
        stored_c = repo.get_by_source(PROCESSES_DATASET, "SYNTHETIC-C")
        assert stored_c is not None and stored_c.id == c_id
        cursor = session.get(SyncCursor, PROCESSES_DATASET)
        assert cursor is not None
        assert (cursor.last_offset, cursor.last_run_id) == (4, resumed.run_id)
        failed = session.get(SyncRun, partial.run_id)
        assert failed is not None and failed.outcome == "failed"
        completed = session.get(SyncRun, resumed.run_id)
        assert completed is not None
        assert completed.outcome == "completed" and completed.records_created == 1
        keys = session.execute(select(Opportunity.source_dataset, Opportunity.source_id)).all()
        assert len(keys) == len(set(keys)) == 4
    print("6. Reanudación: offset inicial=2, creados=1, sin_cambios=1, cursor final=4, total=4")


def test_concurrent_run_does_not_query_secop(postgres_engine: Engine) -> None:
    with (
        Session(postgres_engine) as owner,
        postgres_sync_lock(owner, PROCESSES_DATASET) as acquired,
    ):
        assert acquired
        upstream = FakeHttp([])
        blocked = synchronize(postgres_engine, upstream, resume=True)
        assert (blocked.outcome, blocked.error_kind) == ("failed", "sync_in_progress")
        assert not upstream.calls
    reopened = synchronize(postgres_engine, FakeHttp([FakeResponse([])]))
    assert reopened.outcome == "completed"


def test_daily_command_records_its_window_and_source(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = plan_daily_window(datetime(2026, 11, 5, 11, tzinfo=UTC))
    fake = FakeHttp([FakeResponse([row(id_del_proceso="SYNTHETIC-DAILY")])])
    monkeypatch.setattr("app.db.sync_service.HttpxClient", lambda **kwargs: fake)

    assert run_daily(plan) == 0

    with Session(postgres_engine) as session:
        run = session.scalars(select(SyncRun)).one()
        assert (run.trigger, run.outcome, run.records_created) == ("daily", "completed", 1)
        assert (run.window_start, run.window_end) == (plan.start, plan.end)
        assert session.get(SyncCursor, PROCESSES_DATASET) is None
    assert fake.calls[0]["params"]["$where"].startswith("fecha_de_ultima_publicaci >=")


def test_catalog_migration_backfills_mvp05_rows(postgres_engine: Engine) -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.downgrade(config, "20261122000001")
    source = {
        "departamento_entidad": "Antioquia",
        "ciudad_entidad": "Medellín",
        "fecha_de_recepcion_de": "2026-11-27T11:20:00",
    }
    with postgres_engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO opportunities
                    (source_dataset, source_id, raw_payload, first_seen_at, last_synced_at)
                VALUES ('p6dx-8zbt', 'MVP05-OLD', CAST(:payload AS jsonb), now(), now())
            """),
            {"payload": json.dumps(source)},
        )
    command.upgrade(config, REVISION)
    with Session(postgres_engine) as session:
        item = SqlOpportunityRepository(session).get_by_source(PROCESSES_DATASET, "MVP05-OLD")
        assert item is not None
        assert (item.department, item.city) == ("Antioquia", "Medellín")
        assert item.reception_at == datetime(2026, 11, 27, 11, 20, tzinfo=UTC)
        assert item.raw_payload == source


def test_dossier_migration_blocks_sql_client_roles(postgres_engine: Engine) -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with postgres_engine.begin() as connection:
        connection.execute(text("CREATE ROLE anon"))
        connection.execute(text("CREATE ROLE authenticated"))
        connection.execute(text("ALTER DEFAULT PRIVILEGES GRANT SELECT ON TABLES TO anon"))
        connection.execute(text("ALTER DEFAULT PRIVILEGES GRANT SELECT ON TABLES TO authenticated"))
    command.upgrade(config, "20261122000003")
    with postgres_engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT relrowsecurity, has_table_privilege('anon', oid, 'SELECT'),
                   has_table_privilege('authenticated', oid, 'SELECT')
            FROM pg_class
            WHERE relname IN ('opportunity_documents', 'opportunity_document_contents')
        """)).all()
        assert rows == [(True, False, False)] * 2

def test_extraction_migration_blocks_sql_client_roles(postgres_engine: Engine) -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with postgres_engine.begin() as connection:
        connection.execute(text("CREATE ROLE anon"))
        connection.execute(text("CREATE ROLE authenticated"))
        connection.execute(text("ALTER DEFAULT PRIVILEGES GRANT SELECT ON TABLES TO anon"))
        connection.execute(text("ALTER DEFAULT PRIVILEGES GRANT SELECT ON TABLES TO authenticated"))
    command.upgrade(config, "20261122000004")
    with postgres_engine.connect() as connection:
        row = connection.execute(text("""
            SELECT relrowsecurity, has_table_privilege('anon', oid, 'SELECT'),
                   has_table_privilege('authenticated', oid, 'SELECT')
            FROM pg_class WHERE relname = 'document_extractions'
        """)).one()
        assert row == (True, False, False)


def test_profile_migration_privacy_and_version_history(postgres_engine: Engine) -> None:
    from fastapi.testclient import TestClient

    from app.auth import AuthServices
    from app.main import create_app
    from tests.test_dossier import ADMIN, ANALYST, Memberships, Scanner, Validator, pdf
    from tests.test_profile import EVIDENCE, HEADERS, PATH

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with postgres_engine.begin() as connection:
        connection.execute(text("CREATE ROLE anon"))
        connection.execute(text("CREATE ROLE authenticated"))
        connection.execute(text("ALTER DEFAULT PRIVILEGES GRANT SELECT ON TABLES TO anon"))
        connection.execute(text("ALTER DEFAULT PRIVILEGES GRANT SELECT ON TABLES TO authenticated"))
    command.upgrade(config, "20261122000005")
    with postgres_engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT relrowsecurity, has_table_privilege('anon', oid, 'SELECT'),
                   has_table_privilege('authenticated', oid, 'SELECT')
            FROM pg_class WHERE relname IN ('company_profile_versions', 'company_profile_evidence')
        """)).all()
        assert rows == [(True, False, False)] * 2

    app = create_app(Settings(), auth_services=AuthServices(Validator(), Memberships()))
    app.state.document_services = replace(app.state.document_services, scanner=Scanner())
    with TestClient(app) as client:
        doc = client.post(EVIDENCE, headers=HEADERS, content=pdf("perfil PostgreSQL")).json()
        entry = {
            "category": "capacidad", "title": "Capacidad sintética", "status": "verificado",
            "evidence": [{"document_id": doc["id"], "locator": "Página 1"}],
        }
        first = client.put(PATH, headers=ADMIN, json={"base_version": 0, "entries": [entry]})
        assert first.status_code == 201
        second = client.put(PATH, headers=ADMIN, json={"base_version": 1, "entries": []})
        assert second.status_code == 201 and second.json()["entries"] == []
        assert client.get(f"{PATH}/versions/1", headers=ANALYST).json() == first.json()
        assert client.get(f"{EVIDENCE}/{doc['id']}", headers=ANALYST).content == pdf(
            "perfil PostgreSQL",
        )
