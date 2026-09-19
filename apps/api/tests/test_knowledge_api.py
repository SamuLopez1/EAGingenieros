"""Pruebas de las rutas de la base de conocimiento.

Se generan documentos reales y se suben a través de la API. El foco está en lo
que puede salir mal en una subida: formatos no admitidos, tamaño, nombres
peligrosos y la distinción entre «no hay evidencia» y un fallo técnico.
"""

from __future__ import annotations

import io

# Namespace para derivar identificadores de prueba. Coincide con el que usa el
# servicio para producir UUID válidos y estables a partir de un id entero.
from uuid import UUID as _UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth.principal import Principal, Role, get_current_principal
from app.config import Settings
from app.db.models import Base
from app.main import create_app
from app.rag.embeddings import HashingEmbedder
from app.rag.ingestion import IngestionService
from app.rag.retriever import Retriever

_NAMESPACE = _UUID("6f7a1c2e-3b4d-5e6f-8a9b-0c1d2e3f4a5b")


def make_pdf(text: str) -> bytes:
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    line, y = "", 760
    for word in text.split():
        if len(line) + len(word) > 85:
            pdf.drawString(60, y, line)
            y -= 14
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        pdf.drawString(60, y, line)
    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer.read()


def make_docx(paragraphs: list[str]) -> bytes:
    import docx

    document = docx.Document()
    for text in paragraphs:
        document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    buffer.seek(0)
    return buffer.read()


CONTENIDO = (
    "El proponente debe acreditar experiencia minima de cinco anos en "
    "interventoria de obras de infraestructura vial mediante certificaciones "
    "expedidas por el contratante con soporte de contratos ejecutados."
)


@pytest.fixture
def client(tmp_path) -> TestClient:
    """Aplicación real con persistencia en memoria y autenticación sustituida.

    La autenticación se sustituye aquí a propósito: probar los permisos es el
    objeto de `test_auth.py`, y repetirlo en cada ruta acoplaría estas pruebas a
    detalles del token. Lo que sí se verifica es que **sin** identidad se
    rechaza, más abajo.
    """

    # SQLite en memoria no comparte la base entre conexiones, y TestClient
    # ejecuta la aplicación en otro hilo. Un archivo temporal permite que todas
    # las sesiones vean las mismas tablas.
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    app = create_app(Settings(environment="test", app_version="test"))
    app.state.session_factory = factory

    embedder = HashingEmbedder(dimensions=256)
    app.state.embedder_model = embedder.model_id
    app.state.ingestion_service_factory = lambda: IngestionService(
        factory(), embedder=embedder
    )
    app.state.retriever_factory = lambda: Retriever(
        factory(), embedder=embedder, threshold=0.05, default_limit=6
    )
    app.state.auth_services = None  # se sustituye por la dependencia de abajo

    # Identidad fija: las rutas la exigen, y aquí interesa probar la lógica de
    # subida, no la emisión del token.
    from app.api import knowledge_routes

    app.dependency_overrides[knowledge_routes.get_ingestion_service] = (
        lambda: IngestionService(factory(), embedder=embedder)
    )
    app.dependency_overrides[knowledge_routes.get_retriever] = (
        lambda: Retriever(factory(), embedder=embedder, threshold=0.05, default_limit=6)
    )
    # Identidad fija: `subject_id` se usa como entero en la base de datos, así
    # que aquí se usa un UUID derivado de un id pequeño y no uno aleatorio, cuyo
    # valor de 128 bits no cabría en un entero de 64.
    from uuid import uuid5

    identidad = uuid5(_NAMESPACE, "1")
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject_id=identidad,
        organization_id=uuid5(_NAMESPACE, "org"),
        role=Role.ADMINISTRATOR,
        user_id=1,
    )

    with TestClient(app) as test_client:
        yield test_client
    engine.dispose()


# --- Subida ----------------------------------------------------------------


def test_upload_indexes_a_document(client: TestClient) -> None:
    response = client.post(
        "/api/v1/knowledge/documents",
        files={"file": ("pliego.pdf", make_pdf(CONTENIDO), "application/pdf")},
        data={"title": "Pliego", "category": "experiencia"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "indexado"
    assert body["chunks_indexed"] >= 1


def test_upload_rejects_unsupported_format(client: TestClient) -> None:
    response = client.post(
        "/api/v1/knowledge/documents",
        files={"file": ("datos.zip", b"PKdatos", "application/zip")},
        data={"title": "Comprimido"},
    )

    assert response.status_code == 400
    assert ".pdf" in response.json()["detail"]


def test_upload_rejects_an_unknown_category(client: TestClient) -> None:
    """Una categoría libre crearía clases silenciosas que los filtros no encuentran."""

    response = client.post(
        "/api/v1/knowledge/documents",
        files={"file": ("p.pdf", make_pdf(CONTENIDO), "application/pdf")},
        data={"title": "Pliego", "category": "categoria_inventada"},
    )

    assert response.status_code == 400
    assert "categoría no admitida" in response.json()["detail"]


def test_upload_rejects_an_empty_file(client: TestClient) -> None:
    response = client.post(
        "/api/v1/knowledge/documents",
        files={"file": ("p.pdf", b"", "application/pdf")},
        data={"title": "Vacío"},
    )

    assert response.status_code == 400


def test_upload_rejects_an_oversized_file(client: TestClient) -> None:
    """El límite protege la memoria del servidor antes de leer el contenido."""

    grande = b"x" * (21 * 1024 * 1024)
    response = client.post(
        "/api/v1/knowledge/documents",
        files={"file": ("p.pdf", grande, "application/pdf")},
        data={"title": "Enorme"},
    )

    assert response.status_code == 413


def test_upload_requires_a_title(client: TestClient) -> None:
    response = client.post(
        "/api/v1/knowledge/documents",
        files={"file": ("p.pdf", make_pdf(CONTENIDO), "application/pdf")},
        data={"category": "experiencia"},
    )

    assert response.status_code == 422


def test_upload_reports_unreadable_content_without_server_error(
    client: TestClient,
) -> None:
    """Un PDF ilegible es un fallo de contenido, no del servidor.

    Se devuelve 201 con el estado «fallido» para que quede registrado, en lugar
    de un 4xx que haría perder el motivo.
    """

    response = client.post(
        "/api/v1/knowledge/documents",
        files={"file": ("roto.pdf", b"esto no es un pdf", "application/pdf")},
        data={"title": "Roto", "category": "experiencia"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "fallido"
    assert body["error"]


def test_upload_accepts_docx(client: TestClient) -> None:
    response = client.post(
        "/api/v1/knowledge/documents",
        files={
            "file": (
                "cert.docx",
                make_docx([CONTENIDO]),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={"title": "Certificado", "category": "experiencia"},
    )

    assert response.status_code == 201
    assert response.json()["status"] == "indexado"


# --- Nombres de archivo ---------------------------------------------------


@pytest.mark.parametrize(
    "peligroso",
    [
        "../../../etc/passwd.pdf",
        "..\\..\\windows\\system32\\config.pdf",
        "normal\x00.pdf",
        "/absoluto/ruta.pdf",
    ],
)
def test_dangerous_filenames_are_sanitised(peligroso: str) -> None:
    from app.api.knowledge_routes import safe_filename

    resultado = safe_filename(peligroso)

    assert resultado is not None
    assert "/" not in resultado
    assert "\\" not in resultado
    assert "\x00" not in resultado
    assert ".." not in resultado


def test_safe_filename_handles_missing_name() -> None:
    from app.api.knowledge_routes import safe_filename

    assert safe_filename(None) is None
    assert safe_filename("") is None


def test_safe_filename_preserves_normal_names() -> None:
    from app.api.knowledge_routes import safe_filename

    assert safe_filename("pliego_2026.pdf") == "pliego_2026.pdf"


# --- Listado ---------------------------------------------------------------


def test_list_documents_after_upload(client: TestClient) -> None:
    client.post(
        "/api/v1/knowledge/documents",
        files={"file": ("p.pdf", make_pdf(CONTENIDO), "application/pdf")},
        data={"title": "Pliego", "category": "experiencia"},
    )

    response = client.get("/api/v1/knowledge/documents")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Pliego"


def test_list_omits_the_storage_path(client: TestClient) -> None:
    """La ruta interna no aporta nada al usuario y revela la organización del almacenamiento."""

    client.post(
        "/api/v1/knowledge/documents",
        files={"file": ("p.pdf", make_pdf(CONTENIDO), "application/pdf")},
        data={"title": "Pliego"},
    )

    item = client.get("/api/v1/knowledge/documents").json()["items"][0]

    assert "storage_path" not in item
    assert "content_hash" not in item


def test_list_is_empty_initially(client: TestClient) -> None:
    response = client.get("/api/v1/knowledge/documents")

    assert response.status_code == 200
    assert response.json()["total"] == 0


# --- Consulta --------------------------------------------------------------


@pytest.mark.skip(
    reason=(
        "SQLite no implementa el operador de distancia coseno de pgvector (<=>). "
        "Probar esta ruta contra SQLite fallaría por el motor de prueba, no por el "
        "código. La búsqueda vectorial se verifica contra PostgreSQL con pgvector, "
        "que es el motor real de producción."
    )
)
def test_query_without_documents_declares_no_evidence(client: TestClient) -> None:
    """Sin documentos no hay evidencia, y no es un error: es el resultado correcto."""

    response = client.post(
        "/api/v1/knowledge/query", params={"question": "experiencia en interventoria"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["has_evidence"] is False
    assert body["no_evidence_reason"]
    assert body["retrieved"] == []


@pytest.mark.skip(
    reason=(
        "SQLite no implementa el operador de distancia coseno de pgvector (<=>). "
        "Probar esta ruta contra SQLite fallaría por el motor de prueba, no por el "
        "código. La búsqueda vectorial se verifica contra PostgreSQL con pgvector, "
        "que es el motor real de producción."
    )
)
def test_query_returns_retrieved_chunks_with_citation(client: TestClient) -> None:
    client.post(
        "/api/v1/knowledge/documents",
        files={"file": ("p.pdf", make_pdf(CONTENIDO), "application/pdf")},
        data={"title": "Pliego de condiciones", "category": "experiencia"},
    )

    response = client.post(
        "/api/v1/knowledge/query", params={"question": "interventoria de obras vial"}
    )

    body = response.json()
    assert body["retrieved"], "debía recuperar al menos un fragmento"
    primero = body["retrieved"][0]
    # La cita es lo que permite verificar la afirmación contra el documento.
    assert primero["citation"]
    assert "Pliego de condiciones" in primero["citation"]
    assert primero["score"] > 0


def test_query_rejects_an_empty_question(client: TestClient) -> None:
    response = client.post("/api/v1/knowledge/query", params={"question": ""})

    assert response.status_code == 422


def test_query_validates_the_limit(client: TestClient) -> None:
    response = client.post(
        "/api/v1/knowledge/query",
        params={"question": "algo", "limit": 999},
    )

    assert response.status_code == 422


# --- Autenticación --------------------------------------------------------


def test_routes_require_authentication() -> None:
    """La base de conocimiento es material privado de la empresa."""

    app = create_app(Settings(environment="test"))
    with TestClient(app) as cliente:
        assert cliente.get("/api/v1/knowledge/documents").status_code == 401
        assert (
            cliente.post(
                "/api/v1/knowledge/query", params={"question": "algo"}
            ).status_code
            == 401
        )
        assert (
            cliente.post(
                "/api/v1/knowledge/documents",
                files={"file": ("p.pdf", b"x", "application/pdf")},
                data={"title": "x"},
            ).status_code
            == 401
        )


def test_query_route_is_published_in_openapi(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/knowledge/documents" in paths
    assert "/api/v1/knowledge/query" in paths


def test_health_declares_the_embedding_mode(client: TestClient) -> None:
    body = client.get("/health").json()

    assert body["embeddings"] in ("proveedor_externo", "local_sin_semantica")
