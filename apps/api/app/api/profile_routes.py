"""Rutas del perfil empresarial.

El perfil es material privado de la empresa, así que modificarlo exige rol de
administrador. La lectura no: cualquier usuario autenticado necesita saber si el
perfil está listo antes de confiar en un análisis.

La lógica de versionado y de evidencia vive en `ProfileService`; aquí solo se
traduce entre HTTP y ese servicio.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.profile_dependencies import ProfileDep, require_administrator
from app.api.schemas.profile import (
    CreateVersionRequest,
    ProfileReadinessResponse,
    ProfileVersionResponse,
    SectionReadinessResponse,
)
from app.auth.principal import CurrentPrincipal
from app.profile.service import ProfileError

router = APIRouter(prefix="/api/v1/profile", tags=["perfil"])




@router.get(
    "/readiness",
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
    "/versions",
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
    "/versions",
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

    require_administrator(principal)
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
