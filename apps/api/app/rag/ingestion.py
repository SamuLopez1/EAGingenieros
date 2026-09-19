"""Ingesta de documentos en la base de conocimiento.

Encadena lo que ya existe: extraer texto, fragmentarlo, calcular vectores y
guardarlo indexado. Es el punto donde un documento deja de ser un archivo y pasa
a ser evidencia consultable.

Decisiones:

1. **Reindexar no duplica.** Si el mismo contenido —mismo hash— ya está
   indexado, se reutiliza en lugar de volver a calcular vectores. Recalcular
   consume cuota de embeddings sin mejorar nada.
2. **Una versión nueva no borra la anterior.** Reemplazar un certificado crea
   una versión y deja la previa como no vigente, para que un análisis ya
   aprobado siga apuntando a la evidencia que usó.
3. **Un documento que falla no queda como indexado.** Se registra el motivo y su
   estado queda en «fallido», visible en lugar de silencioso.
4. **Los fragmentos se escriben en una sola transacción.** Un documento a medio
   indexar es peor que uno no indexado: la búsqueda devolvería fragmentos
   sueltos de un documento incompleto sin saberlo.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.knowledge_models import KnowledgeChunk, KnowledgeDocument
from app.documents.extraction import ExtractionResult, ExtractionStatus, extract
from app.documents.validation import AntivirusScanner, validate_upload
from app.rag.chunking import chunk_text
from app.rag.retriever import Embedder


class IngestionError(RuntimeError):
    """No se pudo incorporar el documento."""


@dataclass
class IngestionOutcome:
    """Resultado de incorporar un documento."""

    document_id: int | None
    status: str
    chunks_indexed: int = 0
    reused_existing: bool = False
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status in ("indexado", "reutilizado")


def content_hash(data: bytes) -> str:
    """Hash del contenido, para detectar resubidas sin cambios."""

    return hashlib.sha256(data).hexdigest()


class IngestionService:
    """Incorpora documentos y los deja consultables."""

    def __init__(
        self,
        session: Session,
        *,
        embedder: Embedder,
        # Guarda el archivo y devuelve su ruta. Se inyecta para no acoplar la
        # ingesta al mecanismo de almacenamiento.
        store: Callable[[bytes, str, str | None], str] | None = None,
        scanner: AntivirusScanner | None = None,
        require_antivirus: bool = False,
        max_bytes: int = 20 * 1024 * 1024,
    ) -> None:
        self._db = session
        self._embedder = embedder
        self._store = store
        # La validación se repite aquí aunque la ruta ya la haya hecho: la
        # ingesta es pública y puede invocarse desde un script o una tarea
        # programada. Confiar en que quien llama validó convierte la barrera en
        # opcional sin que nadie lo note.
        self._scanner = scanner
        self._require_antivirus = require_antivirus
        self._max_bytes = max_bytes

    def commit(self) -> None:
        """Confirma la transacción.

        Se expone en lugar de dejar que quien llama acceda a la sesión: el
        servicio hace `flush` para obtener identificadores durante la ingesta,
        pero confirmar es una decisión del límite transaccional y debe ser
        explícita. Los llamadores que no confirmen pierden el trabajo al cerrar
        la sesión.
        """

        self._db.commit()

    def _existing_by_hash(self, digest: str) -> KnowledgeDocument | None:
        return self._db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.content_hash == digest,
                KnowledgeDocument.is_current.is_(True),
                KnowledgeDocument.index_status == "indexado",
            )
        ).scalar_one_or_none()

    def ingest(
        self,
        data: bytes,
        *,
        title: str,
        category: str = "no_clasificado",
        filename: str | None = None,
        content_type: str | None = None,
        valid_until: datetime | None = None,
        uploaded_by: int | None = None,
        enable_ocr: bool = True,
        ocr_language: str = "spa",
        replaces: int | None = None,
    ) -> IngestionOutcome:
        """Extrae, fragmenta, vectoriza y persiste un documento."""

        # Validación y cuarentena. Va antes del hash para no calcular nada
        # sobre contenido que no debería procesarse.
        validation = validate_upload(
            data,
            filename=filename,
            declared_content_type=content_type,
            max_bytes=self._max_bytes,
            scanner=self._scanner,
            require_antivirus=self._require_antivirus,
        )
        if not validation.accepted:
            return IngestionOutcome(
                document_id=None,
                status="rechazado",
                warnings=list(validation.warnings),
                error=(
                    f"{validation.reason}: {validation.detail}"
                    if validation.reason
                    else validation.detail
                ),
            )

        digest = content_hash(data)

        # Mismo contenido ya indexado: se reutiliza. No se recalcula el vector
        # porque el resultado sería idéntico y consume cuota sin aportar nada.
        existing = self._existing_by_hash(digest)
        if existing is not None and replaces is None:
            return IngestionOutcome(
                document_id=existing.id,
                status="reutilizado",
                reused_existing=True,
                chunks_indexed=len(existing.chunks),
                warnings=[
                    f"el contenido ya estaba indexado como «{existing.title}» "
                    "(mismo hash); no se recalcularon vectores"
                ],
            )

        extraction: ExtractionResult = extract(
            data,
            filename,
            content_type=content_type,
            enable_ocr=enable_ocr,
            ocr_language=ocr_language,
        )

        document = KnowledgeDocument(
            title=title[:300],
            category=category,
            original_filename=filename,
            storage_path=self._store(data, digest, filename) if self._store else "",
            content_hash=digest,
            size_bytes=len(data),
            verification_status="pendiente",
            valid_until=valid_until,
            index_status="pendiente",
            uploaded_by=uploaded_by,
            is_current=True,
        )
        self._db.add(document)
        self._db.flush()

        # Reemplazo: la versión anterior deja de ser vigente, pero se conserva
        # para que los análisis ya aprobados sigan apuntando a su evidencia.
        if replaces is not None:
            previous = self._db.get(KnowledgeDocument, replaces)
            if previous is not None:
                previous.is_current = False
                previous.replaced_by_id = document.id
                document.version = previous.version + 1

        if extraction.status is ExtractionStatus.UNSUPPORTED:
            document.index_status = "fallido"
            document.index_error = extraction.error
            self._db.flush()
            return IngestionOutcome(
                document_id=document.id,
                status="no_soportado",
                error=extraction.error,
            )

        if not extraction.is_usable:
            document.index_status = "fallido"
            document.index_error = extraction.error or "no se obtuvo texto utilizable"
            self._db.flush()
            return IngestionOutcome(
                document_id=document.id,
                status="fallido",
                warnings=list(extraction.warnings),
                error=document.index_error,
            )

        chunks = chunk_text(extraction.text)
        if not chunks:
            document.index_status = "fallido"
            document.index_error = "el documento no produjo fragmentos indexables"
            self._db.flush()
            return IngestionOutcome(
                document_id=document.id,
                status="fallido",
                warnings=list(extraction.warnings),
                error=document.index_error,
            )

        # Los vectores se calculan en un lote: una llamada por fragmento
        # multiplicaría la latencia sin mejorar el resultado.
        try:
            vectors = self._embedder.embed([c.content for c in chunks])
        except Exception as error:  # noqa: BLE001 - el proveedor lanza tipos variados
            document.index_status = "fallido"
            # El mensaje se acota: puede contener la URL del proveedor con la
            # clave de API incluida.
            document.index_error = f"fallo al calcular vectores: {type(error).__name__}"
            self._db.flush()
            return IngestionOutcome(
                document_id=document.id,
                status="fallido",
                error=document.index_error,
            )

        if len(vectors) != len(chunks):
            document.index_status = "fallido"
            document.index_error = (
                f"el proveedor devolvió {len(vectors)} vectores para {len(chunks)} fragmentos"
            )
            self._db.flush()
            return IngestionOutcome(
                document_id=document.id, status="fallido", error=document.index_error
            )

        model = self._embedder.model_id
        for chunk, vector in zip(chunks, vectors, strict=True):
            self._db.add(
                KnowledgeChunk(
                    document_id=document.id,
                    ordinal=chunk.ordinal,
                    content=chunk.content,
                    locator=chunk.locator,
                    page_number=chunk.page_number,
                    section=chunk.section,
                    token_estimate=chunk.token_estimate,
                    embedding_model=model,
                    embedding=vector,
                )
            )

        document.index_status = "indexado"
        self._db.flush()

        return IngestionOutcome(
            document_id=document.id,
            status="indexado",
            chunks_indexed=len(chunks),
            warnings=list(validation.warnings) + list(extraction.warnings),
        )

    def reindex(
        self,
        document_id: int,
        *,
        data: bytes,
        filename: str | None = None,
        enable_ocr: bool = True,
        **kwargs: object,
    ) -> IngestionOutcome:
        """Vuelve a indexar un documento con el modelo actual.

        Se borran los fragmentos anteriores antes de recalcular: dejar los
        antiguos mezclaría vectores de dos modelos en el mismo documento y la
        búsqueda devolvería resultados arbitrarios sin error visible.
        """

        document = self._db.get(KnowledgeDocument, document_id)
        if document is None:
            raise IngestionError(f"el documento {document_id} no existe")

        self._db.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id)
        )
        document.index_status = "pendiente"
        self._db.flush()

        return self.ingest(
            data,
            title=document.title,
            category=document.category,
            filename=filename or document.original_filename,
            replaces=None,
            enable_ocr=enable_ocr,
        )

    def documents_pending_reindex(self, *, model_id: str) -> list[KnowledgeDocument]:
        """Documentos indexados con otro modelo.

        Sirven para saber qué falta reindexar tras cambiar de modelo de
        representación, en lugar de descubrirlo porque las consultas devuelven
        resultados sin sentido.
        """

        statement = (
            select(KnowledgeDocument)
            .join(KnowledgeChunk, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(KnowledgeDocument.is_current.is_(True))
            .where(KnowledgeChunk.embedding_model != model_id)
            .distinct()
        )
        return list(self._db.execute(statement).scalars().all())
