"""Rutas HTTP de oportunidades y sincronización.

Estado actual del acceso: estas rutas **no están protegidas todavía**. El
trabajo de autenticación existe en el PR #19 y aún no se ha fusionado; hasta
que lo haga, la aplicación no debe exponerse fuera de un entorno local.

Se deja constancia explícita en lugar de dar por hecho que la protección
llegará: una ruta de negocio sin autorización no debe pasar inadvertida.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.contracts import (
    OpportunityPage,
    OpportunitySummary,
    SyncRunSummary,
    SyncTriggerResponse,
)
from app.db.repository import OpportunityRepository
from app.db.sync_service import SyncRequest, SyncService

router = APIRouter(prefix="/api/v1", tags=["oportunidades"])


def get_repository(request: Request) -> OpportunityRepository:
    """Repositorio configurado en la aplicación."""

    repository = cast(
        "OpportunityRepository | None",
        getattr(request.app.state, "opportunity_repository", None),
    )
    if repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La persistencia no está configurada.",
        )
    return repository


def get_sync_service(request: Request) -> SyncService:
    factory = cast(
        "Callable[[], SyncService] | None",
        getattr(request.app.state, "sync_service_factory", None),
    )
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La sincronización no está configurada.",
        )
    return factory()


RepositoryDep = Annotated[OpportunityRepository, Depends(get_repository)]
SyncServiceDep = Annotated[SyncService, Depends(get_sync_service)]


@router.get(
    "/opportunities",
    response_model=OpportunityPage,
    summary="Listar oportunidades sincronizadas",
)
def list_opportunities(
    repository: RepositoryDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OpportunityPage:
    """Devuelve las oportunidades de la más reciente a la más antigua.

    Las filas sin fecha de publicación se ordenan al final: mostrarlas primero
    daría a entender que son lo más reciente.
    """

    items = repository.list_recent(limit=limit, offset=offset)
    return OpportunityPage(
        items=[OpportunitySummary.model_validate(item) for item in items],
        total=repository.count(),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/opportunities/{opportunity_id}",
    response_model=OpportunitySummary,
    summary="Consultar una oportunidad",
    responses={404: {"description": "La oportunidad no existe"}},
)
def get_opportunity(opportunity_id: int, repository: RepositoryDep) -> OpportunitySummary:
    found = repository.get_by_id(opportunity_id)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La oportunidad no existe.",
        )
    return OpportunitySummary.model_validate(found)


@router.post(
    "/sync-runs",
    response_model=SyncTriggerResponse,
    summary="Ejecutar una sincronización manual",
    responses={503: {"description": "La sincronización no está configurada"}},
)
def trigger_sync(
    sync_service: SyncServiceDep,
    limit: Annotated[int | None, Query(ge=1, le=1000)] = None,
    resume: bool = False,
) -> SyncTriggerResponse:
    """Ejecuta una sincronización acotada y devuelve su resultado.

    Un fallo del proveedor no se devuelve como error HTTP: se responde con el
    resultado de la ejecución para que quede registrado y visible. Ocultarlo
    tras un 500 haría perder el detalle de qué ocurrió.
    """

    outcome = sync_service.run(SyncRequest(limit=limit, resume=resume))
    return SyncTriggerResponse(
        outcome=outcome.outcome,
        run_id=outcome.run_id,
        records_seen=outcome.records_seen,
        records_created=outcome.records_created,
        records_updated=outcome.records_updated,
        records_unchanged=outcome.records_unchanged,
        requests_made=outcome.requests_made,
        last_offset=outcome.last_offset,
        error_kind=outcome.error_kind,
        notes=outcome.notes,
    )


@router.get(
    "/sync-runs",
    response_model=list[SyncRunSummary],
    summary="Consultar el historial de sincronizaciones",
)
def list_sync_runs(
    sync_service: SyncServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[SyncRunSummary]:
    """Historial reciente, del más nuevo al más antiguo."""

    runs = sync_service.recent_runs(limit=limit)
    return [SyncRunSummary.model_validate(run) for run in runs]
