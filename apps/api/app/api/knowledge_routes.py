"""Rutas de la base de conocimiento: subida, listado y consulta.

Advertencia de seguridad vigente: **estas rutas todavía no validan el contenido
de los archivos** —no hay antivirus ni cuarentena (fase F5, HU-13)—. El módulo de
extracción procesa lo que recibe. Por eso la subida está restringida a formatos
conocidos, con límite de tamaño y exigiendo autenticación, y **no debe
exponerse a usuarios no confiables hasta que la cuarentena exista**.

La lista de comprobaciones que sí se aplican aquí:

- autenticación obligatoria: la base de conocimiento es material privado;
- extensión dentro de la lista soportada;
- tamaño máximo, comprobado **antes** de leer el archivo en memoria;
- nombre saneado, para que no pueda escapar de su directorio.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, cast

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)

from app.api.contracts import (
    IngestionResponse,
    KnowledgeDocumentPage,
    KnowledgeDocumentSummary,
    QueryResponse,
    RetrievedChunkResponse,
    SupportedClaimResponse,
)
from app.auth.principal import CurrentPrincipal
from app.db.knowledge_models import KnowledgeDocument
from app.rag.answering import assemble_answer
from app.rag.ingestion import IngestionService
from app.rag.retriever import Retriever

router = APIRouter(prefix="/api/v1/knowledge", tags=["conocimiento"])

# 20 MB, coherente con el límite acordado para el proyecto.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xlsm"}

# Categorías admitidas. Una categoría libre permitiría que un error de tecleo
# creara una clase nueva silenciosa y los filtros dejarían de encontrarla.
ALLOWED_CATEGORIES = {
    "experiencia",
    "personal",
    "financiero",
    "legal",
    "tecnico",
    "no_clasificado",
}

_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


def safe_filename(name: str | None) -> str | None:
    """Reduce el nombre a algo que no pueda escapar de su directorio.

    Un nombre como `../../etc/passwd` o uno con bytes nulos no debe llegar nunca
    al sistema de archivos. Se conserva solo lo que es inequívocamente un nombre.
    """

    if not name:
        return None
    base = Path(name).name  # descarta cualquier componente de ruta
    cleaned = _UNSAFE_NAME.sub("_", base).strip("._")
    return cleaned[:200] or None


def get_ingestion_service(request: Request) -> IngestionService:
    factory = cast(
        "Callable[[], IngestionService] | None",
        getattr(request.app.state, "ingestion_service_factory", None),
    )
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La base de conocimiento no está configurada.",
        )
    return factory()


def get_retriever(request: Request) -> Retriever:
    factory = cast(
        "Callable[[], Retriever] | None",
        getattr(request.app.state, "retriever_factory", None),
    )
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El recuperador no está configurado.",
        )
    return factory()


IngestionDep = Annotated[IngestionService, Depends(get_ingestion_service)]
RetrieverDep = Annotated[Retriever, Depends(get_retriever)]


@router.post(
    "/documents",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Subir un documento a la base de conocimiento",
    responses={
        400: {"description": "Formato no soportado o archivo inválido"},
        413: {"description": "El archivo supera el tamaño máximo"},
    },
)
async def upload_document(
    request: Request,
    principal: CurrentPrincipal,
    file: Annotated[UploadFile, File(description="PDF, DOCX o XLSX")],
    title: Annotated[str, Form(min_length=1, max_length=300)],
    service: IngestionDep,
    category: Annotated[str, Form()] = "no_clasificado",
    replaces: Annotated[int | None, Form()] = None,
) -> IngestionResponse:
    """Sube un documento y lo deja consultable.

    El tamaño se comprueba **antes** de leer el contenido: leer primero un
    archivo enorme para luego rechazarlo consumiría memoria del servidor sin
    necesidad, y con varias subidas simultáneas bastaría para agotarla.
    """

    filename = safe_filename(file.filename)
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"formato no soportado: {suffix or 'desconocido'}. "
                f"Soportados: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )

    if category not in ALLOWED_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"categoría no admitida: {category}. "
                f"Admitidas: {', '.join(sorted(ALLOWED_CATEGORIES))}"
            ),
        )

    declared = file.size
    if declared is not None and declared > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"el archivo supera el límite de {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"el archivo supera el límite de {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="el archivo está vacío"
        )

    try:
        outcome = service.ingest(
            data,
            title=title,
            category=category,
            filename=filename,
            content_type=file.content_type,
            uploaded_by=principal.user_id,
            replaces=replaces,
        )
        # La ingesta hace `flush` —necesario para obtener los identificadores—
        # pero no `commit`: sin confirmar aquí, al cerrar la sesión la
        # transacción se descarta y el documento se pierde en silencio.
        service.commit()
    except Exception as error:  # noqa: BLE001 - ningún fallo debe escapar sin declararse
        # El tipo se incluye porque ayuda a diagnosticar; el mensaje no, porque
        # puede contener rutas internas o detalles del proveedor.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"no fue posible procesar el documento ({type(error).__name__})",
        ) from None

    if outcome.status in ("no_soportado", "fallido"):
        # Un fallo de procesamiento no es un error del servidor: el archivo
        # llegó bien y no se pudo interpretar. Se devuelve 201 con el estado y
        # el motivo, para que quede registrado en lugar de perderse tras un 4xx.
        return IngestionResponse(
            document_id=outcome.document_id,
            status=outcome.status,
            warnings=outcome.warnings,
            error=outcome.error,
        )

    return IngestionResponse(
        document_id=outcome.document_id,
        status=outcome.status,
        chunks_indexed=outcome.chunks_indexed,
        reused_existing=outcome.reused_existing,
        warnings=outcome.warnings,
    )


@router.get(
    "/documents",
    response_model=KnowledgeDocumentPage,
    summary="Listar documentos de la base de conocimiento",
)
def list_documents(
    principal: CurrentPrincipal,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    current_only: bool = True,
) -> KnowledgeDocumentPage:
    """Lista los documentos, por defecto solo las versiones vigentes."""

    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La persistencia no está configurada.",
        )

    from sqlalchemy import func, select

    with session_factory() as session:
        statement = select(KnowledgeDocument)
        count_statement = select(func.count(KnowledgeDocument.id))
        if current_only:
            statement = statement.where(KnowledgeDocument.is_current.is_(True))
            count_statement = count_statement.where(KnowledgeDocument.is_current.is_(True))

        total = session.execute(count_statement).scalar() or 0
        rows = (
            session.execute(
                statement.order_by(KnowledgeDocument.id.desc()).limit(limit).offset(offset)
            )
            .scalars()
            .all()
        )

    return KnowledgeDocumentPage(
        items=[KnowledgeDocumentSummary.model_validate(row) for row in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Consultar la base de conocimiento",
)
def query_knowledge(
    principal: CurrentPrincipal,
    retriever: RetrieverDep,
    question: Annotated[str, Query(min_length=1, max_length=1000)],
    limit: Annotated[int, Query(ge=1, le=20)] = 6,
) -> QueryResponse:
    """Responde con evidencia citada, o declara que no la hay.

    `has_evidence=False` no es un error: es el resultado correcto cuando los
    documentos de la empresa no contienen la respuesta. La interfaz debe
    distinguirlo de un fallo técnico.
    """

    retrieval = retriever.retrieve(question, limit=limit)

    # El modelo de lenguaje aún no está conectado, así que la recuperación es lo
    # único que se puede devolver hoy. La respuesta se ensambla igualmente para
    # que el contrato sea el definitivo: cuando se conecte el modelo, solo
    # cambiará el origen de `raw_answer`.
    answer = assemble_answer(question=question, retrieval=retrieval, raw_answer=None)

    return QueryResponse(
        question=answer.question,
        has_evidence=answer.has_evidence,
        claims=[
            SupportedClaimResponse(text=c.text, citations=[x.citation for x in c.citations])
            for c in answer.claims
        ],
        retrieved=[
            RetrievedChunkResponse(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                document_title=c.document_title,
                category=c.category,
                content=c.content,
                locator=c.locator,
                page_number=c.page_number,
                section=c.section,
                score=c.score,
                is_verified=c.is_verified,
                is_expired=c.is_expired,
                citation=c.citation,
            )
            for c in retrieval.chunks
        ],
        rejected_claims=answer.rejected_claims,
        no_evidence_reason=answer.no_evidence_reason,
        notes=answer.notes,
    )
