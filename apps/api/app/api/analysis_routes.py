"""Rutas de análisis: perfil empresarial y grafo de requisitos.

El análisis se ejecuta en el proceso de la petición. Con un pliego de decenas de
páginas puede tardar, así que se acota el número de documentos y el resultado
queda pendiente de revisión humana en cualquier caso: nada avanza a informe sin
aprobación explícita.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.analysis import (
    AnalysisDependencies,
    AnalysisState,
    build_analysis_graph,
)
from app.auth.principal import CurrentPrincipal
from app.profile.service import ProfileError, ProfileService

router = APIRouter(prefix="/api/v1", tags=["análisis"])

MAX_DOCUMENTS_PER_ANALYSIS = 20


def get_profile_service(request: Request) -> ProfileService:
    factory = cast(
        "Callable[[], ProfileService] | None",
        getattr(request.app.state, "profile_service_factory", None),
    )
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El perfil empresarial no está configurado.",
        )
    return factory()


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


ProfileDep = Annotated[ProfileService, Depends(get_profile_service)]
AnalysisDep = Annotated[AnalysisDependencies, Depends(get_analysis_dependencies)]


# --- Contratos -------------------------------------------------------------


class SectionReadinessResponse(BaseModel):
    name: str
    total: int
    verified: int
    with_evidence: int
    expired: int


class ProfileReadinessResponse(BaseModel):
    version_id: int | None
    version: int | None
    total_records: int
    usable_records: int
    is_ready: bool
    sections: list[SectionReadinessResponse]
    notes: list[str]


class ProfileVersionResponse(BaseModel):
    id: int
    version: int
    is_current: bool
    change_reason: str
    summary: str | None
    created_at: datetime


class CreateVersionRequest(BaseModel):
    change_reason: str = Field(min_length=1, max_length=2000)
    summary: str | None = Field(default=None, max_length=2000)
    copy_from_current: bool = True


class ExperienceRequest(BaseModel):
    contract_reference: str | None = Field(default=None, max_length=200)
    entity: str | None = None
    object_description: str | None = None
    specialty: str | None = Field(default=None, max_length=200)
    role: str | None = Field(default=None, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    amount: Decimal | None = None
    currency: str | None = Field(default=None, max_length=8)
    evidence_document_id: int | None = None
    evidence_locator: str | None = Field(default=None, max_length=300)
    valid_until: date | None = None


class CapabilityRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=120)
    description: str | None = None
    quantity: Decimal | None = None
    unit: str | None = Field(default=None, max_length=40)
    evidence_document_id: int | None = None
    evidence_locator: str | None = Field(default=None, max_length=300)
    valid_until: date | None = None


class FinancialRequest(BaseModel):
    indicator: str = Field(min_length=1, max_length=120)
    period: str = Field(min_length=1, max_length=32)
    value: Decimal | None = None
    unit: str | None = Field(default=None, max_length=40)
    formula: str | None = None
    evidence_document_id: int | None = None
    evidence_locator: str | None = Field(default=None, max_length=300)
    valid_until: date | None = None


class RecordResponse(BaseModel):
    id: int
    supports_claim: bool


class VerifyRequest(BaseModel):
    status: str = Field(pattern="^(pendiente|verificado|rechazado)$")


class AnalyzeRequest(BaseModel):
    opportunity_id: int
    document_ids: list[int] = Field(min_length=1)


class RequirementResponse(BaseModel):
    text: str
    category: str | None
    source_document_id: int | None
    source_locator: str | None
    quote: str | None
    citation_verified: bool
    validation_note: str | None


class MatchResponse(BaseModel):
    requirement_index: int
    state: str
    rationale: str | None
    evidence_chunk_ids: list[int]


class StepResponse(BaseModel):
    node: str
    status: str
    detail: str | None


class AnalysisResponse(BaseModel):
    opportunity_id: int
    documents_read: int
    chunks_available: int
    requirements: list[RequirementResponse]
    matches: list[MatchResponse]
    steps: list[StepResponse]
    rejected_requirements: int
    awaiting_review: bool
    review_reason: str | None
    error: str | None


# --- Perfil ----------------------------------------------------------------


@router.get(
    "/profile/readiness",
    response_model=ProfileReadinessResponse,
    summary="Preparación del perfil empresarial",
)
def profile_readiness(
    principal: CurrentPrincipal, profile: ProfileDep
) -> ProfileReadinessResponse:
    """Indica cuántos datos pueden sustentar un cumplimiento y cuántos no.

    Un perfil a medias produce comparaciones engañosas, así que conviene saberlo
    antes de analizar.
    """

    readiness = profile.readiness()
    return ProfileReadinessResponse(
        version_id=readiness.version_id,
        version=readiness.version,
        total_records=readiness.total_records,
        usable_records=readiness.usable_records,
        is_ready=readiness.is_ready,
        sections=[
            SectionReadinessResponse(
                name=s.name,
                total=s.total,
                verified=s.verified,
                with_evidence=s.with_evidence,
                expired=s.expired,
            )
            for s in readiness.sections
        ],
        notes=readiness.notes,
    )


@router.get(
    "/profile/versions",
    response_model=list[ProfileVersionResponse],
    summary="Historial de versiones del perfil",
)
def profile_versions(
    principal: CurrentPrincipal, profile: ProfileDep
) -> list[ProfileVersionResponse]:
    return [
        ProfileVersionResponse(
            id=v.id,
            version=v.version,
            is_current=v.is_current,
            change_reason=v.change_reason,
            summary=v.summary,
            created_at=v.created_at,
        )
        for v in profile.list_versions()
    ]


@router.post(
    "/profile/versions",
    response_model=ProfileVersionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una versión del perfil",
)
def create_profile_version(
    payload: CreateVersionRequest,
    principal: CurrentPrincipal,
    profile: ProfileDep,
) -> ProfileVersionResponse:
    """Crea una versión nueva. El motivo es obligatorio.

    Un historial sin motivo no permite auditar por qué un cumplimiento cambió de
    resultado entre dos análisis.
    """

    if not principal.is_administrator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un administrador puede modificar el perfil.",
        )
    try:
        version = profile.create_version(
            change_reason=payload.change_reason,
            summary=payload.summary,
            created_by=principal.user_id,
            copy_from_current=payload.copy_from_current,
        )
        profile.commit()
    except ProfileError as error:
        profile.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from None

    return ProfileVersionResponse(
        id=version.id,
        version=version.version,
        is_current=version.is_current,
        change_reason=version.change_reason,
        summary=version.summary,
        created_at=version.created_at,
    )


def _require_version(profile: ProfileService):  # type: ignore[no-untyped-def]
    """Devuelve la versión vigente o falla con un mensaje accionable."""

    current = profile.current()
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "no hay ninguna versión del perfil; cree una antes de añadir datos"
            ),
        )
    return current


@router.post(
    "/profile/experience",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Añadir experiencia al perfil",
)
def add_experience(
    payload: ExperienceRequest, principal: CurrentPrincipal, profile: ProfileDep
) -> RecordResponse:
    if not principal.is_administrator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente."
        )
    version = _require_version(profile)
    record = profile.add_experience(version, **payload.model_dump())
    profile.commit()
    return RecordResponse(id=record.id, supports_claim=record.supports_claim)


@router.post(
    "/profile/capabilities",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Añadir una capacidad al perfil",
)
def add_capability(
    payload: CapabilityRequest, principal: CurrentPrincipal, profile: ProfileDep
) -> RecordResponse:
    if not principal.is_administrator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente."
        )
    version = _require_version(profile)
    record = profile.add_capability(version, **payload.model_dump())
    profile.commit()
    return RecordResponse(id=record.id, supports_claim=record.supports_claim)


@router.post(
    "/profile/financials",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Añadir un indicador financiero al perfil",
)
def add_financial(
    payload: FinancialRequest, principal: CurrentPrincipal, profile: ProfileDep
) -> RecordResponse:
    if not principal.is_administrator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente."
        )
    version = _require_version(profile)
    record = profile.add_financial(version, **payload.model_dump())
    profile.commit()
    return RecordResponse(id=record.id, supports_claim=record.supports_claim)


@router.post(
    "/profile/records/{record_id}/verify",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Verificar un dato del perfil",
)
def verify_record(
    record_id: int,
    payload: VerifyRequest,
    principal: CurrentPrincipal,
    profile: ProfileDep,
) -> None:
    """Marca un dato como verificado.

    La verificación humana es lo que convierte un dato en algo que puede
    sustentar un cumplimiento: adjuntar un documento no garantiza que respalde
    lo afirmado.
    """

    if not principal.is_administrator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente."
        )
    version = _require_version(profile)
    found = None
    for group in (
        version.experience,
        version.personnel,
        version.capabilities,
        version.financials,
        version.legal,
    ):
        for record in group:
            if record.id == record_id:
                found = record
                break
        if found is not None:
            break

    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El dato no existe en la versión vigente del perfil.",
        )

    profile.verify_record(found, status=payload.status, actor_id=principal.user_id)
    profile.commit()


# --- Análisis --------------------------------------------------------------


@router.post(
    "/analyses",
    response_model=AnalysisResponse,
    summary="Analizar una oportunidad con el grafo",
    responses={422: {"description": "No hay documentos analizables"}},
)
def run_analysis(
    payload: AnalyzeRequest,
    principal: CurrentPrincipal,
    request: Request,
    deps: AnalysisDep,
) -> AnalysisResponse:
    """Ejecuta el grafo sobre los documentos indicados.

    El resultado queda **siempre** pendiente de revisión humana: el grafo no
    aprueba nada. Un requisito cuya cita no se pueda verificar queda marcado como
    tal y no sustenta cumplimiento.
    """

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

    return AnalysisResponse(
        opportunity_id=payload.opportunity_id,
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
