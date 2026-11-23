"""Ejercita el límite, la recuperación y los permisos con casos sintéticos."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from app.db.comparison_models import ComparisonRevision
from app.db.document_models import OpportunityDocument, OpportunityDocumentContent
from app.db.extraction_models import DocumentExtraction
from app.db.models import Opportunity
from app.db.profile_models import ProfileEvidence, ProfileVersion
from app.db.report_models import ReportDelivery
from app.db.retention_models import RetentionTombstone
from app.db.session import create_session_factory
from app.documents.extraction import Fragment, Locator, Result
from app.documents.extraction_worker import run_one
from app.operations.retention import overview, purge, replay
from app.operations.scratch import MIN_AGE, sweep, workspace
from app.operations.staging_smoke import check_access
from tests.test_comparison import comparison_path, request_approval
from tests.test_dossier import ANALYST, api, pdf, upload
from tests.test_dossier import catalog as catalog
from tests.test_reports import RECIPIENT, ROOT, SENDER, prepare_case

KEY = b"retention-test-secret-not-for-staging"
ENVIRONMENT = UUID(int=47)


def counts(engine: Engine) -> tuple[int, ...]:
    tables = (
        OpportunityDocument,
        OpportunityDocumentContent,
        DocumentExtraction,
        ComparisonRevision,
        ReportDelivery,
        ProfileVersion,
        ProfileEvidence,
        Opportunity,
    )
    with Session(engine) as session:
        return tuple(
            session.scalar(select(func.count()).select_from(table)) or 0 for table in tables
        )


def set_boundary(engine: Engine, revision: int, boundary: datetime) -> None:
    with Session(engine) as session, session.begin():
        session.execute(
            update(OpportunityDocument)
            .where(
                OpportunityDocument.opportunity_id == 1,
            )
            .values(retention_until=boundary, uploaded_at=boundary - timedelta(days=30))
        )
        session.execute(update(ComparisonRevision).values(expires_at=boundary))
        session.add(
            ReportDelivery(
                organization_id=UUID(int=1),
                opportunity_id=1,
                revision=revision,
                id=UUID(int=101),
                recipient=RECIPIENT,
                sender=SENDER,
                credential="f" * 64,
                link="https://portal.fixture.invalid/",
                state="incierto",
                created_at=boundary - timedelta(days=1),
                updated_at=boundary,
                expires_at=boundary,
                attempts=[],
            )
        )


def test_expiry_boundary_purge_and_old_report_id(catalog, tmp_path, monkeypatch) -> None:
    client, _, settings, engine, approval = prepare_case(catalog)
    report = f"{ROOT}/{approval['revision']}"
    assert upload(client, 2, "Conservar", pdf("B vigente")).status_code == 201
    assert counts(engine) == (2, 2, 1, 2, 0, 1, 1, 2)
    before = datetime.now(UTC)
    boundary = before + timedelta(days=1)
    instant = [boundary - timedelta(microseconds=1)]
    set_boundary(engine, approval["revision"], boundary)
    for module in ("api.document_routes", "api.comparison_routes", "documents.service"):
        monkeypatch.setattr(f"app.{module}.utcnow", lambda: instant[0])
    assert client.get(report, headers=ANALYST).status_code == 200
    documents = client.get(api(1), headers=ANALYST).json()["documents"]
    assert len(documents) == 1 and documents[0]["status"] == "disponible"
    link = f"{api(1)}/{documents[0]['id']}/download-link"
    assert client.post(link, headers=ANALYST).status_code == 200
    instant[0] = boundary
    documents = client.get(api(1), headers=ANALYST).json()["documents"]
    assert len(documents) == 1 and documents[0]["status"] == "vencido"
    assert client.post(link, headers=ANALYST).status_code == 410
    assert client.get(report, headers=ANALYST).status_code == 409

    ledger = tmp_path / "private-ledger.json"
    with Session(engine) as session:
        session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
        assert overview(session, boundary - timedelta(microseconds=1))["documentos_vencidos"] == 0
        before_counts = overview(session, boundary)
        assert before_counts["documentos_vencidos"] == before_counts["envios_vencidos"] == 1
        assert before_counts["comparaciones_vencidas"] == 2
        assert purge(session, boundary, ledger, KEY, ENVIRONMENT) == {
            "document": 1,
            "comparison": 2,
            "delivery": 1,
        }
        session.commit()
        assert purge(session, boundary, ledger, KEY, ENVIRONMENT) == {}
        session.commit()
    assert counts(engine) == (1, 1, 0, 0, 0, 1, 1, 2)
    assert RECIPIENT not in ledger.read_text() and "señalización" not in ledger.read_text()
    instant[0] = before
    fresh = upload(client, 1, "Pliego nuevo", pdf("A nueva"))
    assert fresh.status_code == 201
    path = f"{api(1)}/{fresh.json()['id']}"
    assert client.post(f"{path}/review", headers=ANALYST).status_code == 200
    assert client.post(f"{path}/extraction", headers=ANALYST).status_code == 202
    assert run_one(
        create_session_factory(engine),
        settings,
        lambda *_: Result(
            status="listo",
            fragments=[
                Fragment(
                    text="Habilitante: Experiencia vial: mínimo 1 año.",
                    locator=Locator(page=2),
                )
            ],
        ),
    )
    draft = client.post(comparison_path(1), headers=ANALYST).json()
    assert draft["revision"] > approval["revision"]
    newer = request_approval(client, comparison_path(1), draft)
    assert newer.status_code == 200
    assert client.get(f"{ROOT}/{newer.json()['revision']}", headers=ANALYST).status_code == 200
    assert client.get(report, headers=ANALYST).status_code == 409


def test_interrupted_purge_requires_valid_replay(catalog, tmp_path) -> None:
    _, _, _, engine, approval = prepare_case(catalog)
    boundary = datetime.now(UTC) + timedelta(days=1)
    set_boundary(engine, approval["revision"], boundary)
    ledger = tmp_path / "ledger.json"
    with Session(engine) as session:
        session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
        assert purge(session, boundary, ledger, KEY, ENVIRONMENT)["document"] == 1
        session.rollback()
        assert counts(engine) == (1, 1, 1, 2, 1, 1, 1, 2)
        with pytest.raises(ValueError, match="Reaplica"):
            purge(session, boundary, ledger, KEY, ENVIRONMENT)
        with pytest.raises(ValueError, match="firma"):
            replay(session, ledger, b"wrong-key", ENVIRONMENT)
        with pytest.raises(ValueError, match="Ambiente"):
            replay(session, ledger, KEY, UUID(int=321))
        session.rollback()
        assert replay(session, ledger, KEY, ENVIRONMENT) == {
            "comparison": 2,
            "delivery": 1,
            "document": 1,
        }
        session.commit()
        assert replay(session, ledger, KEY, ENVIRONMENT) == {}
        assert session.scalar(select(func.count()).select_from(RetentionTombstone)) == 4
        with pytest.raises(FileNotFoundError):
            replay(session, tmp_path / "missing.json", KEY, ENVIRONMENT)


def test_only_old_marked_scratch_is_swept(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    old = tmp_path / "eag-extraction-abc123xy"
    pending = tmp_path / "eag-extraction-nomarker"
    pending.mkdir()
    with workspace(tmp_path) as path:
        created = Path(path)
        created.rename(old)
        timestamp = now.timestamp() - MIN_AGE
        for item in (*old.iterdir(), old):
            os.utime(item, (timestamp, timestamp))
    with workspace(tmp_path) as live:
        assert sweep(tmp_path, now, remove=False) == 1
        assert old.is_dir() and Path(live).is_dir()
        assert sweep(tmp_path, now, remove=True) == 1
        assert not old.exists() and Path(live).is_dir() and pending.is_dir()
        assert sweep(tmp_path, now, remove=True) == 0


def test_access_smoke_against_asgi_with_synthetic_accounts(catalog) -> None:
    client, _, _, _, approval = prepare_case(catalog)
    results = check_access(client, "analyst", "admin", f"{ROOT}/{approval['revision']}")
    assert len(results) == 15
    assert results["anonimo_informe"] == 401
    assert results["analista_bandeja"] == 403
    assert results["administrador_bandeja"] == 200
