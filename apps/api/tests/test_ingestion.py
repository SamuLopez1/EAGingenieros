"""Pruebas de ingesta de documentos.

Se generan documentos reales y se indexan en SQLite (sin vectores, porque el
tipo vectorial es propio de PostgreSQL). Lo que se verifica aquí es la lógica de
la ingesta: idempotencia, versionado, estados de fallo y reindexación.

La búsqueda vectorial se verifica aparte contra PostgreSQL con pgvector.
"""

from __future__ import annotations

import io

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.knowledge_models import EMBEDDING_DIMENSIONS, KnowledgeChunk, KnowledgeDocument
from app.db.models import Base
from app.rag.ingestion import IngestionService, content_hash


class FakeEmbedder:
    model_id = "fake-embed-v1"

    def __init__(self, fail: bool = False, wrong_count: bool = False) -> None:
        self.fail = fail
        self.wrong_count = wrong_count
        self.calls = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("el proveedor de embeddings no responde")
        vectors = []
        for text in texts:
            vector = [0.0] * EMBEDDING_DIMENSIONS
            vector[len(text) % EMBEDDING_DIMENSIONS] = 1.0
            vectors.append(vector)
        if self.wrong_count:
            return vectors[:-1] if len(vectors) > 1 else []
        return vectors


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def make_docx(paragraphs: list[str]) -> bytes:
    import docx

    document = docx.Document()
    for text in paragraphs:
        document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    buffer.seek(0)
    return buffer.read()


def make_pdf_text() -> bytes:
    """PDF con texto suficiente para superar el umbral de densidad."""

    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    lines = [
        "PLIEGO DE CONDICIONES PARA LA CONTRATACION DE SERVICIOS.",
        "El proponente debe acreditar experiencia minima de cinco anos en",
        "interventoria de obras de infraestructura vial, mediante certificaciones",
        "expedidas por el contratante con soporte de contratos ejecutados.",
    ]
    y = 760
    for line in lines:
        pdf.drawString(60, y, line)
        y -= 16
    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer.read()


# --- Ingesta correcta ------------------------------------------------------


def test_ingest_indexes_a_docx(db: Session) -> None:
    service = IngestionService(db, embedder=FakeEmbedder())
    data = make_docx(
        [
            "El proponente debe acreditar experiencia minima de cinco anos "
            "en interventoria de obras de infraestructura vial con soporte documental."
        ]
    )

    outcome = service.ingest(
        data, title="Certificado", category="experiencia", filename="certificado.docx"
    )

    assert outcome.succeeded, outcome.error
    assert outcome.chunks_indexed >= 1
    document = db.get(KnowledgeDocument, outcome.document_id)
    assert document is not None
    assert document.index_status == "indexado"
    assert document.category == "experiencia"


def test_ingest_creates_chunks_with_locators(db: Session) -> None:
    service = IngestionService(db, embedder=FakeEmbedder())
    data = make_pdf_text()

    outcome = service.ingest(data, title="Pliego", filename="pliego.pdf")

    chunks = (
        db.execute(
            select(KnowledgeChunk).where(KnowledgeChunk.document_id == outcome.document_id)
        )
        .scalars()
        .all()
    )
    assert chunks
    # El localizador es lo que permite verificar una cita contra el documento.
    assert any(c.locator for c in chunks)
    assert any(c.page_number is not None for c in chunks)


def test_chunks_record_the_embedding_model(db: Session) -> None:
    """Sin el modelo por fragmento, mezclar espacios vectoriales sería silencioso."""

    embedder = FakeEmbedder()
    service = IngestionService(db, embedder=embedder)
    outcome = service.ingest(make_pdf_text(), title="Pliego", filename="p.pdf")

    chunks = (
        db.execute(
            select(KnowledgeChunk).where(KnowledgeChunk.document_id == outcome.document_id)
        )
        .scalars()
        .all()
    )
    assert all(c.embedding_model == embedder.model_id for c in chunks)


# --- Idempotencia ----------------------------------------------------------


def test_resubmitting_identical_content_reuses_the_index(db: Session) -> None:
    """Mismo hash: no se recalculan vectores, que consumiría cuota sin aportar nada."""

    embedder = FakeEmbedder()
    service = IngestionService(db, embedder=embedder)
    data = make_pdf_text()

    first = service.ingest(data, title="Pliego", filename="p.pdf")
    calls_after_first = embedder.calls
    second = service.ingest(data, title="Pliego otra vez", filename="p.pdf")

    assert first.document_id == second.document_id
    assert second.reused_existing
    assert second.status == "reutilizado"
    assert embedder.calls == calls_after_first, "no debió recalcular vectores"
    assert any("mismo hash" in w for w in second.warnings)


def test_different_content_creates_a_new_document(db: Session) -> None:
    service = IngestionService(db, embedder=FakeEmbedder())

    first = service.ingest(make_pdf_text(), title="A", filename="a.pdf")
    second = service.ingest(
        make_docx(["Contenido completamente distinto sobre requisitos financieros."]),
        title="B",
        filename="b.docx",
    )

    assert first.document_id != second.document_id


def test_content_hash_is_stable() -> None:
    assert content_hash(b"datos") == content_hash(b"datos")
    assert content_hash(b"datos") != content_hash(b"otro")


# --- Versionado ------------------------------------------------------------


def test_replacing_a_document_keeps_the_previous_version(db: Session) -> None:
    """Un análisis ya aprobado debe seguir apuntando a la evidencia que usó."""

    service = IngestionService(db, embedder=FakeEmbedder())
    original = service.ingest(make_pdf_text(), title="Certificado v1", filename="c.pdf")
    assert original.document_id is not None

    replacement = service.ingest(
        make_docx(["Certificado actualizado con vigencia prorrogada hasta 2027."]),
        title="Certificado v2",
        filename="c2.docx",
        replaces=original.document_id,
    )

    previous = db.get(KnowledgeDocument, original.document_id)
    current = db.get(KnowledgeDocument, replacement.document_id)
    assert previous is not None and current is not None
    assert previous.is_current is False
    assert previous.replaced_by_id == current.id
    assert current.is_current is True
    assert current.version == previous.version + 1


def test_replaced_document_keeps_its_chunks(db: Session) -> None:
    """Borrar los fragmentos anteriores rompería las citas de análisis ya aprobados."""

    service = IngestionService(db, embedder=FakeEmbedder())
    original = service.ingest(make_pdf_text(), title="v1", filename="c.pdf")
    service.ingest(
        make_docx(["Contenido nuevo del certificado actualizado."]),
        title="v2",
        filename="c2.docx",
        replaces=original.document_id,
    )

    chunks = (
        db.execute(
            select(KnowledgeChunk).where(KnowledgeChunk.document_id == original.document_id)
        )
        .scalars()
        .all()
    )
    assert chunks, "los fragmentos de la versión anterior deben conservarse"


# --- Fallos ----------------------------------------------------------------


def test_unsupported_format_is_reported(db: Session) -> None:
    service = IngestionService(db, embedder=FakeEmbedder())

    outcome = service.ingest(b"PKdatos", title="Comprimido", filename="x.zip")

    assert outcome.status == "no_soportado"
    assert not outcome.succeeded
    assert ".pdf" in (outcome.error or "")


def test_unsupported_document_is_not_marked_as_indexed(db: Session) -> None:
    """Un fallo silencioso sería peor: pasaría por documento indexado."""

    service = IngestionService(db, embedder=FakeEmbedder())
    outcome = service.ingest(b"basura", title="Roto", filename="r.pdf")

    document = db.get(KnowledgeDocument, outcome.document_id)
    assert document is not None
    assert document.index_status == "fallido"
    assert document.index_error


def test_embedding_failure_is_reported(db: Session) -> None:
    service = IngestionService(db, embedder=FakeEmbedder(fail=True))

    outcome = service.ingest(make_pdf_text(), title="Pliego", filename="p.pdf")

    assert outcome.status == "fallido"
    assert not outcome.succeeded
    document = db.get(KnowledgeDocument, outcome.document_id)
    assert document is not None
    assert document.index_status == "fallido"


def test_embedding_failure_does_not_leak_provider_details(db: Session) -> None:
    """El error del proveedor puede incluir la URL con la clave de API."""

    service = IngestionService(db, embedder=FakeEmbedder(fail=True))

    outcome = service.ingest(make_pdf_text(), title="Pliego", filename="p.pdf")

    assert "http" not in (outcome.error or "").lower()
    assert "key" not in (outcome.error or "").lower()


def test_mismatched_vector_count_is_rejected(db: Session) -> None:
    """Menos vectores que fragmentos dejaría fragmentos sin representación."""

    service = IngestionService(db, embedder=FakeEmbedder(wrong_count=True))

    outcome = service.ingest(make_pdf_text(), title="Pliego", filename="p.pdf")

    assert outcome.status == "fallido"
    assert "vectores" in (outcome.error or "")


def test_failed_ingestion_leaves_a_visible_document(db: Session) -> None:
    """El documento debe quedar registrado aunque falle, para poder diagnosticarlo."""

    service = IngestionService(db, embedder=FakeEmbedder(fail=True))

    outcome = service.ingest(make_pdf_text(), title="Pliego", filename="p.pdf")

    assert outcome.document_id is not None
    assert db.get(KnowledgeDocument, outcome.document_id) is not None


# --- Reindexación ----------------------------------------------------------


def test_reindex_removes_previous_chunks(db: Session) -> None:
    """Dejar fragmentos del modelo anterior mezclaría espacios vectoriales."""

    service = IngestionService(db, embedder=FakeEmbedder())
    data = make_pdf_text()
    outcome = service.ingest(data, title="Pliego", filename="p.pdf")
    assert outcome.document_id is not None
    before = len(
        db.execute(
            select(KnowledgeChunk).where(KnowledgeChunk.document_id == outcome.document_id)
        )
        .scalars()
        .all()
    )

    service.reindex(outcome.document_id, data=data, filename="p.pdf")
    after = (
        db.execute(
            select(KnowledgeChunk).where(KnowledgeChunk.document_id == outcome.document_id)
        )
        .scalars()
        .all()
    )

    assert before > 0
    # No se duplican: los números de orden siguen siendo consecutivos sin huecos.
    assert [c.ordinal for c in after] == list(range(len(after)))


def test_reindex_of_missing_document_fails_clearly(db: Session) -> None:
    from app.rag.ingestion import IngestionError

    service = IngestionService(db, embedder=FakeEmbedder())

    with pytest.raises(IngestionError):
        service.reindex(99999, data=b"x")


def test_documents_pending_reindex_detects_model_change(db: Session) -> None:
    """Saber qué falta reindexar evita descubrirlo por resultados sin sentido."""

    service = IngestionService(db, embedder=FakeEmbedder())
    service.ingest(make_pdf_text(), title="Pliego", filename="p.pdf")

    pending = service.documents_pending_reindex(model_id="otro-modelo-v2")
    done = service.documents_pending_reindex(model_id="fake-embed-v1")

    assert len(pending) == 1
    assert done == []
