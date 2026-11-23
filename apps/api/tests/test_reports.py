"""PDF, correo e idempotencia con expedientes y buzones de fixture."""

import io
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import quote
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.report_routes import gateway
from app.comparison import Audit, DocumentBasis, ProfileSource, Row
from app.config import Settings
from app.db.report_models import ReportDelivery
from app.db.session import create_session_factory
from app.documents.extraction import Fragment, Locator, Result
from app.documents.extraction_worker import run_one
from app.documents.requirements import Analysis, Citation, Finding
from app.profile import EvidenceReference
from app.report_mail import Mail, ResendGateway
from app.report_pdf import ApprovedReport, render
from tests.test_comparison import comparison_path, item, request_approval
from tests.test_dossier import ADMIN, ANALYST, OUTSIDER, api, pdf, upload
from tests.test_dossier import catalog as catalog
from tests.test_profile import EVIDENCE, HEADERS, PATH

RECIPIENT = "revisor@fixture.invalid"
SENDER = "informes@fixture.invalid"
ROOT = "/api/v1/opportunities/1/reports"
PROVIDER = UUID(int=887)


def make_sample_report() -> ApprovedReport:
    approved_at = datetime(2026, 11, 22, 15, tzinfo=UTC)
    cite = Citation(
        document_id=UUID(int=41),
        version=2,
        sha256="a" * 64,
        title="Pliego de interventoría",
        locator=Locator(page=4),
        quote="Objeto: Interventoría de puentes y señalización.",
    )
    rows = [
        Row(
            id=str(index),
            kind="habilitante",
            citation=cite.model_copy(
                update={
                    "quote": (
                        f"Requisito {index:02}: Experiencia, señalización y certificación técnica. "
                    )
                    * 4,
                }
            ),
            outcome="cumple" if index % 2 else "revision_manual",
            reason="Revisión de la hipótesis y de la vigencia de la certificación.",
            profile_sources=[
                ProfileSource(
                    index=0,
                    title="Certificación técnica",
                    evidence=[EvidenceReference(document_id=UUID(int=51), locator="página 2")],
                )
            ],
        )
        for index in range(1, 49)
    ]
    return ApprovedReport(
        opportunity_id=92,
        reference="REF-QA",
        title="Interventoría y señalización - caso sintético",
        approval=Audit(
            revision=3,
            action="aprobado",
            actor_id=UUID(int=1),
            actor_role="administrador",
            created_at=approved_at,
            profile_version=4,
            fingerprint="b" * 64,
            document_versions=[DocumentBasis(id=cite.document_id, version=2, sha256=cite.sha256)],
        ),
        analysis=Analysis(
            adapter="fixture",
            fingerprint="f",
            status="revision_manual",
            incomplete=True,
            summary=[Finding(kind="objeto", citation=cite)],
            requirements=[],
            warnings=[],
        ),
        rows=rows,
        expires_at=approved_at + timedelta(days=30),
    )


def test_long_report_pages_and_spanish_text() -> None:
    reader = PdfReader(io.BytesIO(render(make_sample_report())))
    pages = [page.extract_text() for page in reader.pages]
    assert len(pages) >= 4
    assert "Cita del expediente" in pages[0] and "Cita del expediente" in pages[2]
    assert all(page.count("Cita del expediente") <= 1 for page in pages)
    body = " ".join(pages)
    for expected in (
        "señalización",
        "página 4",
        "Aprobador:",
        "Revisión 3",
        "Perfil v4",
        "Requisito 01",
        "Requisito 48",
        "SHA-256",
        "cobertura incompleta",
        "Página 2",
    ):
        assert expected in body


def prepare_case(catalog):
    client, app, settings, engine = catalog
    settings.report_mail_sender = SENDER
    settings.report_mail_recipients = [RECIPIENT]
    settings.report_resend_api_key = None
    settings.report_portal_url = Settings(
        _env_file=None,
        report_portal_url="https://portal.fixture.invalid/",
    ).report_portal_url
    evidence = client.post(EVIDENCE, headers=HEADERS, content=pdf("perfil informe")).json()["id"]
    company = [item("Experiencia vial", evidence, 12)]
    assert (
        client.put(PATH, headers=ADMIN, json={"base_version": 0, "entries": company}).status_code
        == 201
    )
    source = upload(client, 1, quote("Pliego de señalización"), pdf("informe")).json()
    base = f"{api(1)}/{source['id']}"
    assert client.post(f"{base}/review", headers=ANALYST).status_code == 200
    assert client.post(f"{base}/extraction", headers=ANALYST).status_code == 202
    text = chr(10).join(
        ("Objeto: Señalización vial.", "Habilitante: Experiencia vial: mínimo 1 año.")
    )
    assert run_one(
        create_session_factory(engine),
        settings,
        lambda *_: Result(
            status="listo",
            fragments=[Fragment(text=text, locator=Locator(page=2))],
        ),
    )
    draft = client.post(comparison_path(1), headers=ANALYST).json()
    assert client.get(f"{ROOT}/{draft['revision']}", headers=ANALYST).status_code == 409
    assert (
        client.post(
            f"{ROOT}/{draft['revision']}/mail", headers=ADMIN, json={"recipient": RECIPIENT}
        ).status_code
        == 409
    )
    result = request_approval(client, comparison_path(1), draft)
    assert result.status_code == 200
    return client, app, settings, engine, result.json()


def test_report_download_requires_current_exact_revision_and_membership(catalog) -> None:
    client, _, _, _, approval = prepare_case(catalog)
    revision = approval["revision"]
    path = f"{ROOT}/{revision}"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=OUTSIDER).status_code == 403
    assert client.get(path.replace("/1/", "/2/"), headers=ANALYST).status_code == 409
    preview = client.get(path, headers=ANALYST)
    assert preview.status_code == 200 and preview.headers["cache-control"] == "private, no-store"
    assert preview.headers["content-type"] == "application/pdf"
    assert preview.headers["content-disposition"].startswith("inline;")
    response = client.get(f"{path}?download=true", headers=ANALYST)
    assert response.headers["content-disposition"].startswith("attachment;")
    text = " ".join(x.extract_text() for x in PdfReader(io.BytesIO(response.content)).pages)
    assert "Señalización vial." in text and "página 2" in text and "Experiencia vial" in text
    assert "Aprobador:" in text and f"Revisión {revision}" in text
    upload(client, 1, "Adenda", pdf("adenda informe"), kind="adenda")
    assert client.get(path, headers=ANALYST).status_code == 409
    assert (
        client.post(f"{path}/mail", headers=ADMIN, json={"recipient": RECIPIENT}).status_code == 409
    )


def test_mail_lost_reply_reuses_key_and_only_one_provider_acceptance(catalog) -> None:
    client, app, settings, _, approval = prepare_case(catalog)
    path = f"{ROOT}/{approval['revision']}/mail"
    request = {"recipient": RECIPIENT}
    assert client.post(path, headers=ANALYST, json=request).status_code == 403
    assert client.get(path, headers=ANALYST).status_code == 403
    assert client.post(path, headers=OUTSIDER, json=request).status_code == 403
    assert (
        client.post(path, headers=ADMIN, json={"recipient": "ajeno@fixture.invalid"}).status_code
        == 403
    )
    assert client.post(path, headers=ADMIN, json=request).status_code == 503
    settings.report_resend_api_key = SecretStr("fixture-only")
    calls = []
    ledger = {}

    def handler(http_request: httpx.Request) -> httpx.Response:
        body = json.loads(http_request.content)
        key = http_request.headers["Idempotency-Key"]
        assert http_request.url.path == "/emails"
        assert body["from"] == SENDER and body["to"] == [RECIPIENT]
        assert "attachments" not in body and "#informe-aprobado" in body["text"]
        assert "Señalización" not in str(body)
        calls.append(key)
        if key not in ledger:
            ledger[key] = body
            raise httpx.ReadTimeout("respuesta perdida de fixture")
        assert ledger[key] == body
        return httpx.Response(200, json={"id": str(PROVIDER)})

    with httpx.Client(
        base_url="https://fixture.invalid", transport=httpx.MockTransport(handler)
    ) as transport:
        app.dependency_overrides[gateway] = lambda: ResendGateway(transport)
        first = client.post(path, headers=ADMIN, json=request).json()
        second = client.post(path, headers=ADMIN, json={"recipient": RECIPIENT.upper()}).json()
        assert first["state"] == "reintentar" and second["state"] == "aceptado"
        assert second["provider_id"] == str(PROVIDER) and second["id"] == first["id"]
        assert client.post(path, headers=ADMIN, json=request).json() == second
        assert calls == [calls[0], calls[0]] and len(ledger) == 1
        outbox = client.get(path, headers=ADMIN).json()
        assert outbox["recipients"] == [RECIPIENT]
        assert [attempt["state"] for attempt in outbox["deliveries"][0]["attempts"]] == [
            "reintentar",
            "aceptado",
        ]


def test_retry_window_and_attempt_limit_fail_closed(catalog) -> None:
    client, app, settings, engine, approval = prepare_case(catalog)
    settings.report_resend_api_key = SecretStr("fixture-only")
    settings.report_mail_recipients += ["segunda@fixture.invalid"]
    path = f"{ROOT}/{approval['revision']}/mail"
    requests = []

    def fail(request: httpx.Request) -> httpx.Response:
        requests.append(request.headers["Idempotency-Key"])
        return httpx.Response(503)

    with httpx.Client(
        base_url="https://fixture.invalid", transport=httpx.MockTransport(fail)
    ) as transport:
        app.dependency_overrides[gateway] = lambda: ResendGateway(transport)
        for _ in range(2):
            assert (
                client.post(path, headers=ADMIN, json={"recipient": RECIPIENT}).json()["state"]
                == "reintentar"
            )
        with Session(engine) as session:
            record = session.scalar(select(ReportDelivery))
            record.created_at -= timedelta(hours=25)
            session.commit()
        assert (
            client.post(path, headers=ADMIN, json={"recipient": RECIPIENT}).json()["state"]
            == "incierto"
        )
        assert len(requests) == 2 and len(set(requests)) == 1
        second = {"recipient": "segunda@fixture.invalid"}
        states = [client.post(path, headers=ADMIN, json=second).json()["state"] for _ in range(4)]
        assert states == ["reintentar", "reintentar", "incierto", "incierto"]
        assert len(requests) == 5 and len(set(requests)) == 2


@pytest.mark.parametrize(
    ("status", "name", "expected"),
    [
        (409, "concurrent_idempotent_requests", "reintentar"),
        (409, "invalid_idempotent_request", "incierto"),
        (422, "", "rechazado"),
    ],
)
def test_provider_error_contract(status, name, expected) -> None:
    with httpx.Client(
        base_url="https://fixture.invalid",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(status, json={"name": name}),
        ),
    ) as transport:
        assert (
            ResendGateway(transport)
            .send(Mail(SENDER, RECIPIENT, "https://fixture.invalid"), "key")
            .state
            == expected
        )


def test_configuration_requires_exact_mailboxes_and_https() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, report_mail_recipients=["*@fixture.invalid"])
    with pytest.raises(ValidationError):
        Settings(_env_file=None, report_portal_url="http://fixture.invalid")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, report_portal_url="https://fixture.invalid/?token=synthetic")
