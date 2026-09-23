"""Rutas para añadir datos al perfil empresarial.

Separadas de las de lectura y versionado porque cambian por motivos distintos:
estas crecen cada vez que se añade una sección al perfil —personal, legal—,
mientras que las otras cambian si cambia el modelo de versionado.

Las tres rutas comparten la misma forma: comprobar permiso, obtener la versión
vigente, delegar en el servicio y devolver si el dato puede sustentar un
cumplimiento. Esa parte común vive en `_add_record` en lugar de repetirse.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.profile_dependencies import (
    ProfileDep,
    require_administrator,
    require_current_version,
)
from app.api.schemas.profile import (
    CapabilityRequest,
    ExperienceRequest,
    FinancialRequest,
    RecordResponse,
    VerifyRequest,
)
from app.auth.principal import CurrentPrincipal
from app.profile.service import ProfileService

router = APIRouter(prefix="/api/v1/profile", tags=["perfil"])


def _add_record(
    principal: CurrentPrincipal,
    profile: ProfileService,
    kind: str,
    payload: BaseModel,
) -> RecordResponse:
    """Añade un dato a la versión vigente.

    El nombre del método se compone a partir de `kind` para no repetir tres
    rutas idénticas. El servicio expone `add_experience`, `add_capability` y
    `add_financial` con la misma firma, así que la indirección es segura.
    """

    require_administrator(principal)
    version = require_current_version(profile)
    add = getattr(profile, f"add_{kind}")
    record = add(version, **payload.model_dump())
    profile.commit()
    return RecordResponse(id=record.id, supports_claim=record.supports_claim)


@router.post(
    "/experience",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Añadir experiencia al perfil",
)
def add_experience(
    payload: ExperienceRequest, principal: CurrentPrincipal, profile: ProfileDep
) -> RecordResponse:
    return _add_record(principal, profile, "experience", payload)


@router.post(
    "/capabilities",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Añadir una capacidad al perfil",
)
def add_capability(
    payload: CapabilityRequest, principal: CurrentPrincipal, profile: ProfileDep
) -> RecordResponse:
    return _add_record(principal, profile, "capability", payload)


@router.post(
    "/financials",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Añadir un indicador financiero al perfil",
)
def add_financial(
    payload: FinancialRequest, principal: CurrentPrincipal, profile: ProfileDep
) -> RecordResponse:
    return _add_record(principal, profile, "financial", payload)


@router.post(
    "/records/{record_id}/verify",
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

    require_administrator(principal)
    version = require_current_version(profile)

    # Se busca en las cinco secciones: el identificador es único en la base, pero
    # la versión las expone como listas independientes.
    for group in (
        version.experience,
        version.personnel,
        version.capabilities,
        version.financials,
        version.legal,
    ):
        for record in group:
            if record.id == record_id:
                profile.verify_record(
                    record, status=payload.status, actor_id=principal.user_id
                )
                profile.commit()
                return

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="El dato no existe en la versión vigente del perfil.",
    )
