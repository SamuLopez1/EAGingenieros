"""Análisis del expediente autorizado y marcado para revisión."""

from datetime import UTC, datetime
from typing import Literal, cast

from fastapi import APIRouter, Depends, Response

from app.api.document_routes import PRIVATE, DossierDep, ServicesDep, references
from app.api.routes import require_eag_member
from app.documents.extraction_jobs import job_for, view
from app.documents.requirements import (
    MAX_SOURCE_BYTES,
    MAX_SOURCES,
    Analysis,
    OfflineAdapter,
    Source,
    Warning,
    build_analysis,
    fingerprint_for,
)
from app.documents.service import utc

router = APIRouter(
    prefix="/api/v1/opportunities/{opportunity_id}/requirements",
    tags=["requisitos"],
    dependencies=[Depends(require_eag_member)],
)


@router.post("", response_model=Analysis)
def analyze(scope: DossierDep, tools: ServicesDep, response: Response) -> Analysis:
    response.headers["Cache-Control"] = PRIVATE
    return analyze_selected(scope, tools)


def analyze_selected(scope: DossierDep, tools: ServicesDep) -> Analysis:
    documents = scope.items()
    selected = sorted((doc for doc in documents if doc.under_review), key=lambda doc: str(doc.id))
    keys = {doc.document_key for doc in selected}
    now = datetime.now(UTC)
    available = [
        doc for doc in documents if doc.status == "disponible" and utc(doc.retention_until) > now
    ]
    warnings: list[Warning] = []
    if not any(doc.kind == "pliego" and doc.under_review for doc in available):
        warnings.append(Warning(code="sin_pliego_seleccionado"))
    selected_refs = {doc.source_record_id for doc in available if doc.under_review}
    if any(item.source_record_id not in selected_refs for item in references(scope, tools)):
        warnings.append(Warning(code="referencia_oficial_sin_seleccionar"))
    omitted = [doc.id for doc in available if not doc.under_review and doc.document_key not in keys]
    if omitted:
        warnings.append(Warning(code="documentos_sin_seleccionar", documents=omitted))
    for key in sorted(keys):
        revisions = [doc for doc in documents if doc.document_key == key]
        if revisions:
            newest = max(revisions, key=lambda doc: doc.version)
            if not newest.under_review:
                warnings.append(
                    Warning(code="version_mas_reciente_disponible", documents=[newest.id])
                )
    sources: list[Source] = []
    bytes_used = 0
    available_ids = {doc.id for doc in available}
    for doc in selected[:MAX_SOURCES]:
        if doc.id not in available_ids:
            warnings.append(Warning(code="documento_no_disponible", documents=[doc.id]))
            continue
        extraction = view(doc, job_for(scope, doc))
        if extraction.status != "listo":
            warnings.append(Warning(code="extraccion_incompleta", documents=[doc.id]))
        if extraction.result is None:
            continue
        for fragment in extraction.result.fragments:
            size = len(fragment.text.encode())
            if bytes_used + size > MAX_SOURCE_BYTES or len(sources) >= MAX_SOURCES:
                warnings.append(Warning(code="limite_texto_fuente", documents=[doc.id]))
                break
            sources.append(
                Source(
                    document_id=doc.id,
                    version=doc.version,
                    sha256=doc.sha256,
                    title=doc.title,
                    kind=cast(Literal["pliego", "adenda"], doc.kind),
                    locator=fragment.locator,
                    text=fragment.text,
                )
            )
            bytes_used += size
    if len(selected) > MAX_SOURCES:
        warnings.append(Warning(code="limite_documentos"))
    adapter = OfflineAdapter()
    key = fingerprint_for(
        f"{scope.organization_id}/{scope.opportunity.id}/{adapter.version}",
        sources,
        warnings,
    )
    return build_analysis(adapter, key, sources, warnings)
