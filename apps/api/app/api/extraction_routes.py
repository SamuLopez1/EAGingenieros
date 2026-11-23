"""Extracción privada con el mismo alcance que el expediente."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response

from app.api.document_routes import PRIVATE, DossierDep
from app.api.routes import require_eag_member
from app.documents.extraction_jobs import ExtractionView, enqueue, job_for, view

router = APIRouter(
    prefix="/api/v1/opportunities/{opportunity_id}/documents/{document_id}/extraction",
    tags=["extracción"],
    dependencies=[Depends(require_eag_member)],
)


@router.get("", response_model=ExtractionView)
def get_extraction(document_id: UUID, scope: DossierDep, response: Response) -> ExtractionView:
    doc = scope.find(document_id)
    scope.require_ready(doc)
    response.headers["Cache-Control"] = PRIVATE
    return view(doc, job_for(scope, doc))


@router.post("", status_code=202, response_model=ExtractionView)
def request_extraction(
    document_id: UUID, scope: DossierDep, response: Response, retry: bool = False,
) -> ExtractionView:
    response.headers["Cache-Control"] = PRIVATE
    return enqueue(scope, document_id, retry=retry)
