"""Expedientes con persistencia SQL y personas/documentos sintéticos."""

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.auth import AuthServices, Membership, Role
from app.config import Settings
from app.db.document_models import OpportunityDocument, OpportunityDocumentContent
from app.db.models import Base
from app.db.repository import SqlOpportunityRepository
from app.documents.official import OfficialReference
from app.documents.validation import AntivirusUnavailableError, ClamAvScanner
from app.main import create_app
from tests.test_sync_repository import make_record

ADMIN = {"Authorization": "Bearer admin"}
ANALYST = {"Authorization": "Bearer analyst"}
OUTSIDER = {"Authorization": "Bearer other"}


class Validator:
    def subject_from_token(self, access_token: str) -> UUID:
        return UUID(int={"admin": 1, "analyst": 2, "other": 3}[access_token])


class Memberships:
    def resolve(self, subject: UUID, _: str) -> Membership:
        return Membership(
            UUID(int=99 if subject.int == 3 else 1),
            Role.ADMINISTRATOR if subject.int == 1 else Role.ANALYST,
        )


class Scanner:
    engine = "fixture"
    available = True

    def __init__(self, clean: bool = True) -> None:
        self.clean = clean

    def scan(self, _: bytes) -> tuple[bool, str | None]:
        return self.clean, None if self.clean else "sintético"


def pdf(marker: str) -> bytes:
    return f"%PDF-1.4\n% Documento sintético {marker}\n%%EOF\n".encode()


@pytest.fixture
def catalog(tmp_path: Path):
    url = f"sqlite+pysqlite:///{(tmp_path / 'catalog.sqlite').as_posix()}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = SqlOpportunityRepository(session)
        repo.upsert_many([make_record("MVP07-A"), make_record("MVP07-B")])
        session.commit()
    settings = Settings(
        _env_file=None, database_url=SecretStr(url),
        document_download_secret=SecretStr("fixture-only-for-this-run-123456789"),
    )
    auth = AuthServices(Validator(), Memberships())  # type: ignore[arg-type]
    app = create_app(settings, auth_services=auth)
    app.state.document_services = replace(app.state.document_services, scanner=Scanner())
    with TestClient(app) as client:
        yield client, app, settings, engine
    engine.dispose()


def api(opp: int) -> str:
    return f"/api/v1/opportunities/{opp}/documents"


def upload(client: TestClient, opp: int, label: str, data: bytes, *, kind: str = "pliego",
           name: str = "archivo.pdf", media: str = "application/pdf"):
    return client.post(
        api(opp), params={"kind": kind}, content=data,
        headers={**ANALYST, "X-Document-Name": name, "X-Document-Title": label,
                 "Content-Type": media},
    )


def test_a_b_a_and_download_authorization(catalog) -> None:
    client, _, _, _ = catalog
    assert client.get(api(1)).status_code == 401
    assert client.get(api(1), headers=OUTSIDER).status_code == 403
    assert client.get(api(991), headers=ANALYST).status_code == 404
    assert client.get(api(1), headers=ANALYST).json()["missing_pliego"]
    a = upload(client, 1, "Pliego A", pdf("A"))
    b = upload(client, 2, "Adenda B", pdf("B"), kind="adenda")
    assert a.status_code == b.status_code == 201
    doc_a, doc_b = a.json(), b.json()
    assert doc_a["opportunity_id"] == 1 and doc_b["opportunity_id"] == 2
    assert doc_a["origin"] == "manual" and doc_a["sha256"] == sha256(pdf("A")).hexdigest()
    assert doc_b["kind"] == "adenda"
    assert client.get(api(2), headers=ANALYST).json()["documents"] == [doc_b]
    listing = client.get(api(1), headers=ANALYST)
    assert listing.json()["documents"] == [doc_a]
    assert not listing.json()["missing_pliego"] and listing.json()["official"] == []
    assert listing.headers["cache-control"] == "private, no-store"

    root = f"{api(1)}/{doc_a['id']}"
    grant = client.post(f"{root}/download-link", headers=ANALYST).json()
    path, ticket = grant["url"].split("#")
    assert path == f"{root}/content" and grant["expires_in"] == 60
    headers = {**ANALYST, "X-Document-Ticket": ticket}
    content = client.get(path, headers=headers)
    assert content.content == pdf("A") and content.status_code == 200
    assert content.headers["content-disposition"].startswith("attachment;")
    assert client.get(f"{api(2)}/{doc_a['id']}/content", headers=headers).status_code == 404
    assert client.get(f"{api(2)}/{doc_b['id']}/content", headers=headers).status_code == 403
    assert client.get(path, headers={**headers, **ADMIN}).status_code == 403
    assert client.get(path, headers={**headers, **OUTSIDER}).status_code == 403
    assert client.get(path, headers={"X-Document-Ticket": ticket}).status_code == 401
    expired = {**ANALYST, "X-Document-Ticket": "0." + "a" * 64}
    assert client.get(path, headers=expired).status_code == 403


def test_versions_are_scoped_and_review_is_explicit(catalog) -> None:
    client, _, _, _ = catalog
    first = upload(client, 1, "Pliego", pdf("primero")).json()
    again = upload(client, 1, "PLIEGO", pdf("primero")).json()
    newer = upload(client, 1, "Pliego", pdf("actualizado")).json()
    independent = upload(client, 2, "Pliego", pdf("primero")).json()
    assert first["id"] == again["id"]
    assert [first["version"], newer["version"], independent["version"]] == [1, 2, 1]
    for item in (first, newer):
        response = client.post(f"{api(1)}/{item['id']}/review", headers=ANALYST)
        assert response.status_code == 200 and response.json()["under_review"]
    listed = client.get(api(1), headers=ANALYST).json()["documents"]
    assert [item["id"] for item in listed if item["under_review"]] == [newer["id"]]


def test_quarantine_is_private_until_rescan_and_infected_bytes_are_discarded(catalog) -> None:
    client, app, _, engine = catalog
    app.state.document_services = replace(app.state.document_services, scanner=None)
    response = upload(client, 1, "Pliego retenido", pdf("retenido"))
    assert response.status_code == 201
    doc = response.json()
    assert doc["status"] == "cuarentena"
    path = f"{api(1)}/{doc['id']}"
    assert client.post(f"{path}/download-link", headers=ANALYST).status_code == 409
    assert client.post(f"{path}/review", headers=ANALYST).status_code == 409
    assert client.post(f"{path}/rescan", headers=ANALYST).status_code == 403
    assert client.post(f"{path}/rescan", headers=ADMIN).json()["status"] == "cuarentena"
    app.state.document_services = replace(app.state.document_services, scanner=Scanner(False))
    assert client.post(f"{path}/rescan", headers=ADMIN).json()["status"] == "rechazado"
    with Session(engine) as session:
        assert session.get(OpportunityDocumentContent, UUID(doc["id"])) is None
    assert upload(client, 1, "Pliego infectado", pdf("I")).status_code == 422
    app.state.document_services = replace(app.state.document_services, scanner=Scanner())
    assert upload(client, 1, "Pliego retenido", pdf("retenido")).json()["version"] == 2


def test_limits_and_invalid_uploads_before_storage(catalog) -> None:
    client, _, settings, engine = catalog
    payload = pdf("límite")
    settings.document_max_bytes = len(payload)
    settings.dossier_max_bytes = len(payload) + 3
    assert upload(client, 1, "Grande", payload + b"123").status_code == 413
    assert upload(client, 1, "Inseguro", payload, name="%2E%2E%5Carchivo.pdf").status_code == 422
    assert upload(client, 1, "Simulado", b"MZexe").status_code == 422
    assert upload(client, 1, "MIME", payload, media="text/plain").status_code == 422
    assert upload(client, 1, "ZIP", payload, name="archivo.zip").status_code == 422
    assert upload(client, 1, "Corrupto", b"%PDF-1.4\n").status_code == 422
    assert upload(client, 1, "Pliego", payload).status_code == 201
    assert upload(client, 1, "Adenda", payload, kind="adenda").status_code == 413
    assert upload(client, 2, "Adenda", payload, kind="adenda").status_code == 201
    with Session(engine) as session:
        assert len(session.scalars(select(OpportunityDocument)).all()) == 2


def test_official_only_uses_validated_id_for_exact_opportunity(catalog) -> None:
    client, app, _, _ = catalog
    reference = OfficialReference.model_validate({
        "id": "00000000-0000-0000-0000-000000000009",
        "source_dataset": "p6dx-8zbt", "source_id": "MVP07-A", "source_record_id": "archive-7",
        "kind": "pliego", "title": "Pliego oficial", "filename": "pliego.pdf",
        "url": "https://community.secop.gov.co/synthetic/pliego.pdf",
        "verified_at": "2020-01-01T00:00:00Z", "evidence": "verificación sintética",
    })

    class Downloader:
        def __init__(self) -> None:
            self.requests: list[str] = []

        def read(self, url: str, _: int) -> tuple[bytes, str]:
            self.requests.append(url)
            return pdf("oficial"), "application/pdf"

    donor = Downloader()
    app.state.document_services = replace(
        app.state.document_services, manifest=(reference,), downloader=donor
    )
    assert client.get(api(2), headers=ANALYST).json()["official"] == []
    assert client.post(f"{api(2)}/official/{reference.id}", headers=ANALYST).status_code == 404
    assert donor.requests == []
    available = client.get(api(1), headers=ANALYST).json()["official"]
    assert available[0]["id"] == str(reference.id) and "url" not in available[0]
    endpoint = f"{api(1)}/official/{reference.id}"
    response = client.post(endpoint, headers=ANALYST, json={"url": "http://127.0.0.1/"})
    assert response.status_code == 201
    assert response.json()["origin"] == "oficial"
    assert response.json()["source_record_id"] == "archive-7"
    assert donor.requests == [reference.url]
    repeated = client.post(endpoint, headers=ANALYST).json()
    assert repeated["id"] == response.json()["id"]


@pytest.mark.parametrize(
    ("reply", "expected"),
    [(b"stream: OK\0", True), (b"stream: EICAR FOUND\0", False),
     (b"", None), (b"stream: Error receiving ERROR\0", None), (b"stream: OK", None)],
)
def test_clamd_requires_explicit_complete_reply(monkeypatch, reply: bytes, expected) -> None:
    class ScannerSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def settimeout(self, _):
            pass

        def sendall(self, _):
            pass

        def recv(self, _):
            nonlocal reply
            result, reply = reply, b""
            return result

    monkeypatch.setattr("app.documents.validation.socket.create_connection", lambda *a, **kw: (
        ScannerSocket()
    ))
    scanner = ClamAvScanner()
    if expected is None:
        with pytest.raises(AntivirusUnavailableError):
            scanner.scan(pdf("scanner"))
    else:
        assert scanner.scan(pdf("scanner"))[0] is expected
