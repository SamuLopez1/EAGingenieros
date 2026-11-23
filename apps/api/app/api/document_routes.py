"""Expediente y archivos privados, siempre bajo una oportunidad autorizada."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal, cast
from urllib.parse import quote
from uuid import UUID

from anyio import fail_after
from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes import EagMember, require_eag_administrator, require_eag_member
from app.config import Settings
from app.db.document_models import OpportunityDocument
from app.db.models import Opportunity, utcnow
from app.documents.official import (
    DocumentKind,
    OfficialDownloader,
    OfficialReference,
    SourceError,
    SourceTooLarge,
)
from app.documents.service import (
    TICKET_TTL,
    DocumentError,
    Dossier,
    IncomingDocument,
    Origin,
    filename_from_header,
    title_from_header,
    utc,
)
from app.documents.validation import AntivirusScanner

router = APIRouter(
    prefix="/api/v1/opportunities/{opportunity_id}/documents",
    tags=["expediente"],
    dependencies=[Depends(require_eag_member)],
)
PRIVATE = "private, no-store"


@dataclass(frozen=True)
class DocumentServices:
    scanner: AntivirusScanner | None
    downloader: OfficialDownloader
    manifest: tuple[OfficialReference, ...]


def dossier(request: Request, opportunity_id: int, member: EagMember) -> Iterator[Dossier]:
    factory = cast(
        "sessionmaker[Session] | None",
        getattr(request.app.state, "opportunity_session_factory", None),
    )
    if factory is None:
        raise DocumentError(503, "expediente_no_configurado")
    with factory() as session:
        opportunity = session.get(Opportunity, opportunity_id)
        if opportunity is None:
            raise DocumentError(404, "oportunidad_no_encontrada")
        settings = cast(Settings, request.app.state.opportunity_settings)
        yield Dossier(session, opportunity, member, settings)


DossierDep = Annotated[Dossier, Depends(dossier)]


def services(request: Request) -> DocumentServices:
    return cast(DocumentServices, request.app.state.document_services)


ServicesDep = Annotated[DocumentServices, Depends(services)]


class DocumentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    opportunity_id: int
    kind: DocumentKind
    title: str
    filename: str
    origin: Origin
    source_record_id: str | None
    source_verified_at: datetime | None
    version: int
    sha256: str
    size_bytes: int
    status: Literal["disponible", "cuarentena", "rechazado", "vencido"]
    under_review: bool
    uploaded_at: datetime
    retention_until: datetime


class OfficialView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    kind: DocumentKind
    title: str
    source_record_id: str
    verified_at: datetime


class DossierView(BaseModel):
    documents: list[DocumentView]
    official: list[OfficialView]
    missing_pliego: bool
    max_file_bytes: int


class DownloadLink(BaseModel):
    url: str
    expires_in: int


def view(document: OpportunityDocument) -> DocumentView:
    item = DocumentView.model_validate(document)
    item.uploaded_at = utc(item.uploaded_at)
    item.retention_until = utc(item.retention_until)
    if item.source_verified_at:
        item.source_verified_at = utc(item.source_verified_at)
    if item.retention_until <= utcnow():
        item.status = "vencido"
        item.under_review = False
    return item


def references(scope: Dossier, tools: DocumentServices) -> Iterator[OfficialReference]:
    for item in tools.manifest:
        if (
            item.source_dataset == scope.opportunity.source_dataset
            and item.source_id == scope.opportunity.source_id
            and item.verified_at <= utcnow()
        ):
            yield item


@router.get("", response_model=DossierView)
def list_documents(scope: DossierDep, tools: ServicesDep, response: Response) -> DossierView:
    items = [view(item) for item in scope.items()]
    response.headers["Cache-Control"] = PRIVATE
    return DossierView(
        documents=items,
        official=[OfficialView.model_validate(item) for item in references(scope, tools)],
        missing_pliego=not any(
            item.kind == "pliego" and item.status == "disponible" for item in items
        ),
        max_file_bytes=scope.settings.document_max_bytes,
    )


async def incoming_bytes(request: Request, scope: DossierDep) -> bytes:
    return await read_upload(request, scope.settings.document_max_bytes)


async def read_upload(request: Request, limit: int) -> bytes:
    length = request.headers.get("content-length")
    if length is not None:
        if not length.isascii() or not length.isdecimal() or len(length) > 12:
            raise DocumentError(400, "longitud_invalida")
        if int(length) > limit:
            raise DocumentError(413, "demasiado_grande")
    output = bytearray()
    try:
        with fail_after(45):
            async for chunk in request.stream():
                if len(output) + len(chunk) > limit:
                    raise DocumentError(413, "demasiado_grande")
                output.extend(chunk)
    except TimeoutError:
        raise DocumentError(408, "carga_agotada") from None
    return bytes(output)


@router.post(
    "", response_model=DocumentView, status_code=201,
    openapi_extra={"requestBody": {
        "required": True,
        "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
    }},
)
def upload_document(
    scope: DossierDep,
    tools: ServicesDep,
    request: Request,
    kind: DocumentKind,
    filename: Annotated[str, Header(alias="X-Document-Name", max_length=2400)],
    title: Annotated[str, Header(alias="X-Document-Title", max_length=1800)],
    payload: Annotated[bytes, Depends(incoming_bytes)],
) -> DocumentView:
    return view(scope.save(
        IncomingDocument(
            kind, title_from_header(title), filename_from_header(filename),
            payload, request.headers.get("content-type"),
        ),
        tools.scanner,
    ))


@router.post("/official/{reference_id}", response_model=DocumentView, status_code=201)
def import_official(reference_id: UUID, scope: DossierDep, tools: ServicesDep) -> DocumentView:
    entry = next((item for item in references(scope, tools) if item.id == reference_id), None)
    if entry is None:
        raise DocumentError(404, "asociacion_no_validada")
    try:
        payload, media_type = tools.downloader.read(entry.url, scope.settings.document_max_bytes)
    except SourceTooLarge:
        raise DocumentError(413, "demasiado_grande") from None
    except SourceError:
        raise DocumentError(502, "descarga_oficial_no_disponible") from None
    return view(scope.save(
        IncomingDocument(
            entry.kind, title_from_header(quote(entry.title)),
            filename_from_header(quote(entry.filename, safe="")), payload, media_type, entry,
        ),
        tools.scanner,
    ))


@router.post("/{document_id}/review", response_model=DocumentView)
def select_review(document_id: UUID, scope: DossierDep) -> DocumentView:
    return view(scope.mark_review(document_id))


@router.post(
    "/{document_id}/rescan", response_model=DocumentView,
    dependencies=[Depends(require_eag_administrator)],
)
def rescan(document_id: UUID, scope: DossierDep, tools: ServicesDep) -> DocumentView:
    return view(scope.rescan(document_id, tools.scanner))


@router.post("/{document_id}/download-link", response_model=DownloadLink)
def download_link(document_id: UUID, scope: DossierDep, response: Response) -> DownloadLink:
    ticket = scope.ticket(scope.find(document_id))
    path = f"/api/v1/opportunities/{scope.opportunity.id}/documents/{document_id}/content"
    response.headers["Cache-Control"] = PRIVATE
    return DownloadLink(url=f"{path}#{ticket}", expires_in=TICKET_TTL)


@router.get(
    "/{document_id}/content", response_class=Response,
    responses={200: {"content": {"application/octet-stream": {
        "schema": {"type": "string", "format": "binary"},
    }}}},
)
def download_document(
    document_id: UUID,
    scope: DossierDep,
    ticket: Annotated[str, Header(alias="X-Document-Ticket", max_length=100)],
) -> Response:
    item = scope.find(document_id)
    payload = scope.content(item, ticket)
    return Response(
        payload,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{item.filename}"',
            "Cache-Control": PRIVATE,
            "X-Content-Type-Options": "nosniff",
        },
    )
