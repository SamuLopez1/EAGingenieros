"""Ruta de análisis: ejecuta el grafo sobre los documentos de una oportunidad.

Se separa de las rutas del perfil porque cambia por motivos distintos: esta
cambia si cambia el grafo; aquellas, si cambia el modelo del perfil.

El resultado queda **siempre** pendiente de revisión humana: el grafo propone,
nunca aprueba. Un requisito cuya cita no se pueda verificar queda marcado como
tal y no sustenta cumplimiento.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.analysis import (
    AnalysisDependencies,
    AnalysisState,
    build_analysis_graph,
)
from app.api.schemas.analysis import (
    AnalysisResponse,
    AnalyzeRequest,
    MatchResponse,
    RequirementResponse,
    StepResponse,
)
from app.auth.principal import CurrentPrincipal

router = APIRouter(prefix="/api/v1", tags=["análisis"])

# Tope de documentos por análisis. Un pliego completo puede tener decenas de
# anexos, y procesarlos todos en una sola petición bloquearía el servidor sin
# que nadie lo notara.
MAX_DOCUMENTS_PER_ANALYSIS = 20


def get_analysis_dependencies(request: Request) -> AnalysisDependencies:
    factory = cast(
        "Callable[[], AnalysisDependencies] | None",
        getattr(request.app.state, "analysis_dependencies_factory", None),
    )
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El análisis no está configurado.",
        )
    return factory()


AnalysisDep = Annotated[AnalysisDependencies, Depends(get_analysis_dependencies)]


def _to_response(result: dict) -> AnalysisResponse:  # type: ignore[type-arg]
    """Traduce el estado del grafo al contrato HTTP."""

    return AnalysisResponse(
        opportunity_id=result["opportunity_id"],
        documents_read=result["documents_read"],
        chunks_available=result["chunks_available"],
        requirements=[
            RequirementResponse(
                text=r.text,
                category=r.category,
                source_document_id=r.source_document_id,
                source_locator=r.source_locator,
                quote=r.quote,
                citation_verified=r.citation_verified,
                validation_note=r.validation_note,
            )
            for r in result["requirements"]
        ],
        matches=[
            MatchResponse(
                requirement_index=m.requirement_index,
                state=m.state,
                rationale=m.rationale,
                evidence_chunk_ids=m.evidence_chunk_ids,
            )
            for m in result["matches"]
        ],
        steps=[
            StepResponse(node=s.node, status=s.status, detail=s.detail)
            for s in result["steps"]
        ],
        rejected_requirements=result["rejected_requirements"],
        awaiting_review=result["awaiting_review"],
        review_reason=result["review_reason"],
        error=result["error"],
    )


@router.post(
    "/analyses",
    response_model=AnalysisResponse,
    summary="Analizar una oportunidad con el grafo",
    responses={400: {"description": "Demasiados documentos en una sola petición"}},
)
def run_analysis(
    payload: AnalyzeRequest,
    principal: CurrentPrincipal,
    deps: AnalysisDep,
) -> AnalysisResponse:
    """Ejecuta el grafo sobre los documentos indicados."""

    if len(payload.document_ids) > MAX_DOCUMENTS_PER_ANALYSIS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"se admiten como máximo {MAX_DOCUMENTS_PER_ANALYSIS} documentos "
                "por análisis"
            ),
        )

    from langgraph.checkpoint.memory import MemorySaver

    graph = build_analysis_graph(deps).compile(checkpointer=MemorySaver())
    state = AnalysisState(
        opportunity_id=payload.opportunity_id,
        document_ids=payload.document_ids,
        actor_id=principal.user_id,
    )
    result = graph.invoke(
        state,
        config={"configurable": {"thread_id": f"op-{payload.opportunity_id}"}},
        durability="sync",
    )
    return _to_response(result)
