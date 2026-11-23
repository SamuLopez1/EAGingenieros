"""Rutas HTTP de oportunidades y sincronización.

Todas las rutas requieren una identidad resuelta por el servidor. La
sincronización manual queda reservada al administrador.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session, sessionmaker

from app.api.contracts import (
    OpportunityPage,
    OpportunitySummary,
    SyncRunSummary,
    SyncTriggerResponse,
)
from app.auth import Principal, Role, require_roles
from app.catalog import CatalogQuery
from app.config import Settings
from app.db.repository import OpportunityRepository, SqlOpportunityRepository
from app.db.sync_service import SyncRequest, SyncService
from app.secop.daily import plan_daily_window

router = APIRouter(
    prefix="/api/v1",
    tags=["oportunidades"],
)
EagMember = Annotated[Principal, Depends(require_roles(Role.ADMINISTRATOR, Role.ANALYST))]
Administrator = Annotated[Principal, Depends(require_roles(Role.ADMINISTRATOR))]


def require_eag_member(request: Request, principal: EagMember) -> None:
    settings = cast(Settings, request.app.state.opportunity_settings)
    if principal.membership.organization_id != settings.initial_organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente.")


def require_eag_administrator(request: Request, principal: Administrator) -> None:
    require_eag_member(request, principal)


def get_repository(request: Request) -> Iterator[OpportunityRepository]:
    """Repositorio configurado en la aplicación."""

    repository = cast(
        "OpportunityRepository | None",
        getattr(request.app.state, "opportunity_repository", None),
    )
    if repository is not None:
        yield repository
        return
    factory = cast(
        "sessionmaker[Session] | None",
        getattr(request.app.state, "opportunity_session_factory", None),
    )
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La persistencia no está configurada.",
        )
    with factory() as session:
        yield SqlOpportunityRepository(session)


def get_sync_service(request: Request) -> Iterator[SyncService]:
    factory = cast(
        "Callable[[], SyncService] | None",
        getattr(request.app.state, "sync_service_factory", None),
    )
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La sincronización no está configurada.",
        )
    service = factory()
    try:
        yield service
    finally:
        service.close()


RepositoryDep = Annotated[OpportunityRepository, Depends(get_repository)]
SyncServiceDep = Annotated[SyncService, Depends(get_sync_service)]


@router.get(
    "/opportunities",
    response_model=OpportunityPage,
    summary="Listar oportunidades sincronizadas",
    dependencies=[Depends(require_eag_member)],
)
def list_opportunities(
    request: Request,
    repository: RepositoryDep,
    query: Annotated[CatalogQuery, Query()],
) -> OpportunityPage:
    result = repository.search(query)
    return OpportunityPage(
        items=[OpportunitySummary.model_validate(item) for item in result.items],
        total=result.total,
        limit=query.limit,
        offset=query.offset,
        catalog_synced_at=result.catalog_synced_at,
        latest_sync_outcome=result.latest_sync_outcome,
        latest_sync_finished_at=result.latest_sync_finished_at,
        catalog_stale_after_hours=request.app.state.opportunity_settings.catalog_stale_after_hours,
    )


@router.get("/opportunity-options", dependencies=[Depends(require_eag_member)])
def opportunity_options(repository: RepositoryDep) -> dict[str, list[str]]:
    return repository.options()


@router.get(
    "/opportunities/{opportunity_id}",
    response_model=OpportunitySummary,
    summary="Consultar una oportunidad",
    dependencies=[Depends(require_eag_member)],
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
    dependencies=[Depends(require_eag_administrator)],
    responses={503: {"description": "La sincronización no está configurada"}},
)
def trigger_sync(
    sync_service: SyncServiceDep,
    limit: Annotated[int | None, Query(ge=1, le=1000)] = None,
    resume: bool = False,
    mode: Literal["initial", "incremental"] = "initial",
) -> SyncTriggerResponse:
    """Ejecuta una sincronización acotada y devuelve su resultado.

    Un fallo del proveedor no se devuelve como error HTTP: se responde con el
    resultado de la ejecución para que quede registrado y visible. Ocultarlo
    tras un 500 haría perder el detalle de qué ocurrió.
    """

    if mode == "incremental" and resume and limit is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Para retomar una ventana incremental, omita el límite de filas.",
        )
    window = plan_daily_window(datetime.now(UTC)) if mode == "incremental" else None
    outcome = sync_service.run(SyncRequest(limit=limit, resume=resume, updated_window=window))
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
    dependencies=[Depends(require_eag_member)],
)
def list_sync_runs(
    sync_service: SyncServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[SyncRunSummary]:
    """Historial reciente, del más nuevo al más antiguo."""

    runs = sync_service.recent_runs(limit=limit)
    return [SyncRunSummary.model_validate(run) for run in runs]
