"""API, almacenamiento privado y ejecución local con documentos sintéticos."""

from dataclasses import replace
from datetime import timedelta
from uuid import UUID

from app.db.extraction_models import DocumentExtraction
from app.db.models import utcnow
from app.db.session import create_session_factory
from app.documents.extraction import failed
from app.documents.extraction_jobs import claim_next, finish_claim
from app.documents.extraction_worker import run_one
from tests.test_dossier import ANALYST, OUTSIDER, api, upload
from tests.test_dossier import catalog as catalog
from tests.test_extraction import synthetic_pdf


def extraction_path(opp: int, doc: dict) -> str:
    return f"{api(opp)}/{doc['id']}/extraction"


def test_queue_real_child_idempotence_and_isolation(catalog) -> None:
    client, _, settings, engine = catalog
    factory = create_session_factory(engine)
    markers = [
        "Documento sintetico de oportunidad A, primera version.",
        "Documento sintetico de oportunidad B, primera version.",
        "Documento sintetico de oportunidad A, segunda version.",
    ]
    documents = [
        upload(client, opp, "Pliego", synthetic_pdf(marker)).json()
        for opp, marker in zip([1, 2, 1], markers, strict=True)
    ]
    paths = [extraction_path(doc["opportunity_id"], doc) for doc in documents]
    assert [doc["version"] for doc in documents] == [1, 1, 2]
    spec = client.get("/openapi.json").json()
    route = "/api/v1/opportunities/{opportunity_id}/documents/{document_id}/extraction"
    assert "200" in spec["paths"][route]["get"]["responses"]
    assert "202" in spec["paths"][route]["post"]["responses"]
    assert client.get(paths[0]).status_code == 401
    assert client.post(paths[0], headers=OUTSIDER).status_code == 403
    assert client.get(extraction_path(2, documents[0]), headers=ANALYST).status_code == 404
    for path in paths:
        assert client.get(path, headers=ANALYST).json()["status"] == "sin_extraccion"
        response = client.post(path, headers=ANALYST)
        assert response.status_code == 202
        assert response.json()["status"] == "pendiente"
        assert client.post(path, headers=ANALYST).json()["attempts"] == 0
    for _ in paths:
        assert run_one(factory, settings)
    for index in (0, 1, 2, 0):
        response = client.get(paths[index], headers=ANALYST)
        assert response.headers["cache-control"] == "private, no-store"
        state = response.json()
        doc = documents[index]
        assert state["status"] == "listo"
        assert state["attempts"] == 1
        assert state["document_id"] == doc["id"]
        assert state["opportunity_id"] == doc["opportunity_id"]
        assert state["version"] == doc["version"]
        assert state["source_sha256"] == doc["sha256"]
        assert [(f["locator"]["page"], f["text"]) for f in state["result"]["fragments"]] == [
            (1, markers[index]),
        ]
    repeat = client.post(paths[0], params={"retry": True}, headers=ANALYST).json()
    assert repeat["status"] == "listo"
    assert not run_one(factory, settings)


def test_quarantine_cannot_enqueue_or_read(catalog) -> None:
    client, app, settings, engine = catalog
    app.state.document_services = replace(app.state.document_services, scanner=None)
    doc = upload(client, 1, "Pliego", synthetic_pdf(None)).json()
    path = extraction_path(1, doc)
    assert doc["status"] == "cuarentena"
    assert client.get(path, headers=ANALYST).status_code == 409
    assert client.post(path, headers=ANALYST).status_code == 409
    assert not run_one(create_session_factory(engine), settings)


def test_retry_and_worker_lease_fencing(catalog) -> None:
    client, _, settings, engine = catalog
    factory = create_session_factory(engine)
    doc = upload(client, 1, "Pliego", synthetic_pdf(None)).json()
    path = extraction_path(1, doc)
    client.post(path, headers=ANALYST)
    with factory() as session:
        _, old = claim_next(session, timeout=5, max_bytes=settings.document_max_bytes)
        assert old is not None
        job = session.get(DocumentExtraction, UUID(doc["id"]))
        assert job is not None
        job.lease_until = utcnow() - timedelta(seconds=1)
        session.commit()
        _, new = claim_next(session, timeout=5, max_bytes=settings.document_max_bytes)
        assert new is not None and new.token != old.token
        finish_claim(session, old, failed("worker_fallido"))
        assert client.get(path, headers=ANALYST).json()["status"] == "procesando"
        finish_claim(session, new, failed("tiempo_agotado"))
    last = client.get(path, headers=ANALYST).json()
    assert last["attempts"] == 2 and last["result"]["error_code"] == "tiempo_agotado"
    assert client.post(path, headers=ANALYST).json()["status"] == "fallido"
    retry = client.post(path, params={"retry": True}, headers=ANALYST).json()
    assert retry["status"] == "pendiente" and retry["attempts"] == 0
    assert run_one(factory, settings, lambda *_: failed("tiempo_agotado"))
    assert client.get(path, headers=ANALYST).json()["status"] == "pendiente"
    assert run_one(factory, settings, lambda *_: failed("tiempo_agotado"))
    assert client.get(path, headers=ANALYST).json()["status"] == "fallido"
