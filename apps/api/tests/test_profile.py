"""Pruebas del perfil privado con identidad y evidencias sintéticas."""

from dataclasses import replace
from hashlib import sha256
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import utcnow
from app.db.profile_models import ProfileEvidence, ProfileVersion
from tests.test_dossier import ADMIN, ANALYST, OUTSIDER, pdf
from tests.test_dossier import catalog as catalog

PATH = "/api/v1/company-profile"
EVIDENCE = f"{PATH}/evidence"
HEADERS = {**ADMIN, "Content-Type": "application/pdf", "X-Document-Name": "fixture.pdf"}


def test_permissions_evidence_and_immutable_versions(catalog) -> None:
    client, _, _, engine = catalog
    assert client.get(PATH).status_code == 401
    assert client.get(PATH, headers=OUTSIDER).status_code == 403
    forbidden = client.put(PATH, headers=ANALYST, json={"base_version": 0, "entries": []})
    assert forbidden.status_code == 403
    forbidden_upload = client.post(EVIDENCE, headers={**HEADERS, **ANALYST}, content=pdf("QA"))
    assert forbidden_upload.status_code == 403
    initial = client.get(PATH, headers=ANALYST)
    assert initial.headers["cache-control"] == "private, no-store"
    assert initial.json()["version"] == 0 and initial.json()["availability_status"] == "pendiente"

    uploaded = client.post(EVIDENCE, headers=HEADERS, content=pdf("QA"))
    assert uploaded.status_code == 201
    evidence_id = uploaded.json()["id"]
    assert client.post(EVIDENCE, headers=HEADERS, content=pdf("QA")).json()["id"] == evidence_id
    evidence_path = f"{EVIDENCE}/{evidence_id}"
    assert client.get(evidence_path, headers=OUTSIDER).status_code == 403
    assert client.get(evidence_path).status_code == 401
    assert client.get(evidence_path, headers=ANALYST).content == pdf("QA")

    availability = {"category": "disponibilidad", "title": "Cuadrilla QA", "role": "Inspector"}
    capability = {
        "category": "capacidad", "title": "Topografía sintética", "status": "verificado",
        "service_line": "Estudios",
        "evidence": [{"document_id": evidence_id, "locator": "Página 2"}],
    }
    entries = [availability, capability]
    first = client.put(PATH, headers=ADMIN, json={"base_version": 0, "entries": entries})
    assert first.status_code == 201
    assert first.json()["author_id"] == str(UUID(int=1))
    assert first.json()["entries"][0]["dedication_percent"] is None
    assert first.json()["availability_status"] == "pendiente"
    second = client.put(PATH, headers=ADMIN, json={
        "base_version": 1, "entries": [{
            **availability, "dedication_percent": 0, "status": "verificado",
            "starts_on": "2026-12-01", "ends_on": "2026-12-31", "evidence": capability["evidence"],
        }],
    })
    assert second.status_code == 201 and second.json()["availability_status"] == "verificado"
    assert second.json()["entries"][0]["dedication_percent"] == "0"
    stale = client.put(PATH, headers=ADMIN, json={"base_version": 1, "entries": []})
    assert stale.status_code == 409
    history = client.get(f"{PATH}/versions", headers=ANALYST).json()
    assert [item["version"] for item in history] == [2, 1]
    assert client.get(f"{PATH}/versions?before=2", headers=ANALYST).json() == history[1:]
    assert client.get(f"{PATH}/versions/1", headers=ANALYST).json() == first.json()
    assert client.get(PATH, headers=ANALYST).json() == second.json()
    assert client.get(f"{PATH}/versions/1", headers=OUTSIDER).status_code == 403
    with Session(engine) as session:
        assert session.get(ProfileVersion, (UUID(int=99), 1)) is None
        assert session.get(ProfileEvidence, UUID(evidence_id)).organization_id == UUID(int=1)


def test_profile_validation_and_unavailable_antivirus(catalog) -> None:
    client, app, _, _ = catalog
    entries = [
        {"category": "capacidad", "title": "Sin respaldo", "status": "verificado"},
        {"category": "equipo", "title": "Vigencia invertida", "starts_on": "2026-12-02",
         "ends_on": "2026-12-01"},
        {"category": "disponibilidad", "title": "Límite", "role": "QA", "dedication_percent": 101},
        {"category": "disponibilidad", "title": "Sin cargo"},
        {"category": "financiero", "title": "Sin unidad", "amount": "0"},
        {"category": "capacidad", "title": "Ajena", "evidence": [
            {"document_id": str(UUID(int=99)), "locator": "Página 1"},
        ]},
    ]
    for entry in entries:
        response = client.put(PATH, headers=ADMIN, json={"base_version": 0, "entries": [entry]})
        assert response.status_code == 422
    assert client.get(PATH, headers=ADMIN).json()["version"] == 0
    app.state.document_services = replace(app.state.document_services, scanner=None)
    assert client.post(EVIDENCE, headers=HEADERS, content=pdf("sin antivirus")).status_code == 503


def test_members_cannot_read_or_link_rows_from_another_organization(catalog) -> None:
    client, _, _, engine = catalog
    document_id = UUID(int=41)
    payload = pdf("otra organización sintética")
    with Session(engine) as session:
        session.add(ProfileEvidence(
            id=document_id, organization_id=UUID(int=99), author_id=UUID(int=43),
            filename="otra.pdf", sha256=sha256(payload).hexdigest(),
            created_at=utcnow(), payload=payload,
        ))
        session.add(ProfileVersion(
            organization_id=UUID(int=99), version=1, author_id=UUID(int=43),
            created_at=utcnow(), entries=[],
        ))
        session.commit()
    assert client.get(f"{EVIDENCE}/{document_id}", headers=ANALYST).status_code == 404
    assert client.get(f"{PATH}/versions/1", headers=ANALYST).status_code == 404
    response = client.put(PATH, headers=ADMIN, json={"base_version": 0, "entries": [{
        "category": "capacidad", "title": "Referencia ajena", "status": "verificado",
        "evidence": [{"document_id": str(document_id), "locator": "Página 1"}],
    }]})
    assert response.status_code == 422
