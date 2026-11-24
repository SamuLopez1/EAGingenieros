"""Caso público reproducible para grabar Liciscope. Importado solo por --recording."""

import time
from datetime import UTC, datetime
from hashlib import sha256
from html import escape
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from app.api.report_routes import gateway
from app.db.models import SyncRun
from app.db.profile_models import ProfileEvidence, ProfileVersion
from app.db.repository import SqlOpportunityRepository
from app.documents.official import OfficialReference
from app.profile import Entry, EvidenceReference
from app.report_mail import Mail, ProviderResult
from app.secop.client import normalise_record
from fastapi.responses import HTMLResponse
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

SOURCE = "CO1.REQ.11405993"
REFERENCE = "CM-06-IN-006-2026"
DOCUMENT = UUID("583eb7d5-de8f-4a62-b9c5-4652f75f68a1")
PDF_URL = (
    "https://community.secop.gov.co/Public/Archive/RetrieveFile/Index?"
    "DocUniqueIdentifier=&DocumentId=894696463&InCommunity=False&InPaymentGateway=False"
)
PDF_SHA = "a6f01faa1a4ebba3777299c47919811bba1a52c9e78878fa870ed3e79745b2d0"
RECIPIENT = "buzon@liciscope.invalid"


def seed(engine, organization):
    now = datetime.now(UTC)
    with httpx.Client(timeout=15, trust_env=False) as client:
        response = client.get(
            "https://www.datos.gov.co/resource/p6dx-8zbt.json",
            params={"id_del_proceso": SOURCE, "$limit": 2},
        )
        response.raise_for_status()
        rows = response.json()
    assert len(rows) == 1 and rows[0]["referencia_del_proceso"].startswith(REFERENCE)
    assert "CO1.NTC.11260034" in rows[0]["urlproceso"]["url"]
    record = normalise_record(rows[0], fetched_at=now)
    assert record is not None
    profile_id = UUID(int=41)
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(60, 750, "Liciscope | EVIDENCIA SINTÉTICA · ejercicio académico")
    pdf.drawString(60, 716, "Formato 3 de experiencia: borrador de práctica, sin valor probatorio.")
    pdf.save()
    data = buffer.getvalue()
    with Session(engine) as session:
        repo = SqlOpportunityRepository(session)
        repo.upsert_many([record])
        assert repo.count() == 1
        session.add(
            SyncRun(
                dataset="p6dx-8zbt",
                trigger="manual",
                outcome="completed",
                started_at=now,
                finished_at=datetime.now(UTC),
                records_seen=1,
                records_created=1,
                requests_made=1,
            )
        )
        session.add(
            ProfileEvidence(
                id=profile_id,
                organization_id=organization,
                author_id=UUID(int=2),
                created_at=now,
                filename="liciscope-evidencia-sintetica.pdf",
                sha256=sha256(data).hexdigest(),
                payload=data,
            )
        )
        entry = Entry(
            category="experiencia",
            title="Formato 3 de experiencia · evidencia sintética",
            status="pendiente",
            evidence=[EvidenceReference(document_id=profile_id, locator="Página 1 (sintética)")],
        )
        session.add(
            ProfileVersion(
                organization_id=organization,
                version=1,
                author_id=UUID(int=2),
                created_at=now,
                entries=[entry.model_dump(mode="json")],
            )
        )
        session.commit()


def settings(manifest: Path):
    import json

    reference = OfficialReference(
        id=DOCUMENT,
        source_dataset="p6dx-8zbt",
        source_id=SOURCE,
        source_record_id="894696463",
        kind="pliego",
        title="Documento base definitivo · CM-06-IN-006-2026",
        filename="pliego-definitivo-cm-06-in-006-2026.pdf",
        url=PDF_URL,
        verified_at=datetime.now(UTC),
        evidence="Archivo público SECOP II 894696463; el pliego identifica CM-06-IN-006-2026. "
        "La fase de oferta CO1.REQ.11405993 corresponde al aviso CO1.NTC.11260034.",
    )
    manifest.write_text(json.dumps([reference.model_dump(mode="json")]), encoding="utf-8")
    return dict(
        company_name="Liciscope",
        official_document_manifest=manifest,
        document_clamav_host="127.0.0.1",
        document_clamav_port=13310,
        report_resend_api_key="demo-local-only",
        report_mail_sender="informes@liciscope.invalid",
        report_mail_recipients=[RECIPIENT],
        report_portal_url="https://liciscope.invalid/",
    )


def attach_mailbox(app, port: int) -> dict[str, Mail]:
    inbox: dict[str, Mail] = {}

    class LocalGateway:
        def send(self, mail: Mail, key: str) -> ProviderResult:
            # Simular pérdida de respuesta después de una única aceptación.
            first = key not in inbox
            inbox.setdefault(key, mail)
            return ProviderResult("reintentar" if first else "aceptado", UUID(int=887))

    @app.get("/demo-mailbox", include_in_schema=False)
    def mailbox():
        messages = []
        for mail in inbox.copy().values():
            target = urlsplit(mail.link)
            link = f"http://127.0.0.1:{port}/?{target.query}#{target.fragment}"
            messages.append(
                f"<article><h2>Liciscope · Informe aprobado disponible</h2>"
                f"<p>Entrega de prueba. El portal exige iniciar sesión.</p>"
                f'<a href="{escape(link, quote=True)}">Abrir el informe privado</a></article>'
            )
        count = (
            "1 mensaje de prueba" if len(messages) == 1 else f"{len(messages)} mensajes de prueba"
        )
        body = "".join(messages) or "<p>Aún no hay mensajes de prueba.</p>"
        return HTMLResponse(
            '<!doctype html><html lang="es"><meta charset="utf-8">'
            "<title>Buzón simulado · Liciscope</title>"
            '<main style="max-width:42rem;margin:3rem auto;font:1.15rem system-ui">'
            f"<h1>Buzón simulado</h1><p>{count}</p>{body}</main></html>",
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )

    app.dependency_overrides[gateway] = LocalGateway
    return inbox


def rehearse(origin: str, auth: str, inbox: dict[str, Mail]) -> None:
    with httpx.Client(base_url=origin, timeout=30, trust_env=False) as client:
        token = (
            client.post(
                f"{auth}/auth/v1/token?grant_type=password",
                json={
                    "email": "admin@fixture.invalid",
                    "password": "Synthetic-Only-06",
                },
            )
            .raise_for_status()
            .json()["access_token"]
        )
        headers = {"Authorization": "Bearer " + token}

        def call(method, path, **kw):
            response = client.request(method, "/api" + path, headers=headers, **kw)
            if not response.is_success:
                raise RuntimeError(
                    f"Ensayo Liciscope: {method} {path} devolvió {response.status_code}"
                )
            return response

        assert call("GET", "/auth/session").json()["role"] == "administrador"
        rows = call("GET", "/api/v1/opportunities").json()
        (row,) = rows["items"]
        assert rows["total"] == 1 and row["source_id"] == SOURCE
        base = f"/api/v1/opportunities/{row['id']}"
        docs = base + "/documents"
        doc = call("POST", f"{docs}/official/{DOCUMENT}").json()
        assert doc["status"] == "disponible" and doc["sha256"] == PDF_SHA
        assert doc["opportunity_id"] == row["id"] and doc["origin"] == "oficial"
        path = f"{docs}/{doc['id']}"
        call("POST", path + "/review")
        call("POST", path + "/extraction")
        deadline = time.monotonic() + 65
        while time.monotonic() < deadline:
            extraction = call("GET", path + "/extraction").json()
            if extraction["status"] not in {"pendiente", "procesando", "en_cola"}:
                break
            time.sleep(0.4)
        assert extraction["status"] in {"listo", "revision"} and extraction["result"]["fragments"]
        analysis = call("POST", base + "/requirements").json()
        citation = analysis["summary"][0]["citation"]
        requirement = analysis["requirements"][0]["citation"]
        for cite in (citation, requirement):
            assert cite["locator"]["page"] > 0 and cite["document_id"] == doc["id"]
        draft = call("POST", base + "/comparison").json()
        assert draft["rows"]
        approved = call(
            "POST",
            base + "/comparison/approve",
            json={
                "revision": draft["revision"],
                "fingerprint": draft["fingerprint"],
                "reason": "Ensayo académico con perfil sintético.",
            },
        ).json()
        report = f"{base}/reports/{approved['revision']}"
        saved = call("GET", report + "?download=true")
        assert "attachment" in saved.headers["content-disposition"]
        cover = PdfReader(BytesIO(saved.content)).pages[0].extract_text()
        assert "LICISCOPE" in cover and REFERENCE in cover
        assert client.get("/api" + report).status_code == 401
        for state in ("reintentar", "aceptado", "aceptado"):
            assert (
                call("POST", report + "/mail", json={"recipient": RECIPIENT}).json()["state"]
                == state
            )
        assert len(inbox) == 1 and "1 mensaje de prueba" in call("GET", "/demo-mailbox").text
        profile_path = "/api/v1/company-profile"
        profile = call("GET", profile_path).json()
        call(
            "PUT",
            profile_path,
            json={
                "base_version": profile["version"],
                "entries": profile["entries"],
            },
        )
        assert client.get("/api" + report, headers=headers).status_code == 409
        call("POST", base + "/comparison")  # dejar borrador listo para la grabación
        inbox.clear()
        print(
            f"LICISCOPE_OK ficha={row['id']} fuente={SOURCE} pliego=disponible "
            f"resumen_pagina={citation['locator']['page']} "
            f"requisito_pagina={requirement['locator']['page']} "
            f"resultado={draft['rows'][0]['outcome']} pdf=200 anonimo=401 invalidado=409 buzon=1",
            flush=True,
        )
