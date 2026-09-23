"""Rutas HTTP de oportunidades, fuentes y sincronización.

Acceso
------
Estas rutas están protegidas. Hasta ahora no lo estaban, y el propio docstring
de este módulo lo advertía: «una ruta de negocio sin autorización no debe pasar
inadvertida». La autorización vive aquí y no en RLS, porque la API se conecta
con un rol privilegiado que omite RLS por diseño.

Los datos de una oportunidad son comercialmente sensibles —qué licitaciones
sigue una empresa y con qué documentos— así que **todo** el router exige
identidad resuelta, incluidas la lectura y la sincronización. No hay rutas
públicas de negocio.

Sobre la sincronización: se permite a cualquier usuario autenticado, no solo al
administrador. Es una operación normal del analista y limitarla obligaría a
pedir ayuda para algo cotidiano. Lo que sí queda acotado es su alcance: cada
ejecución respeta el tope de peticiones configurado.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.contracts import (
    OpportunityPage,
    OpportunitySummary,
    SourceCoverage,
    SourceCoverageResponse,
    SyncRunSummary,
    SyncTriggerResponse,
)
from app.auth.principal import CurrentPrincipal
from app.db.repository import OpportunityFilters, OpportunityRepository
from app.db.sync_service import SyncRequest, SyncService
from app.secop.sources import SOURCES, UnknownSourceError, get_source

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


def get_sync_service_factory(
    request: Request,
) -> Callable[[str | None], SyncService]:
    """Fábrica de servicios de sincronización, una por fuente.

    Recibe el conjunto de datos porque el sistema tiene más de una fuente y cada
    una necesita su propio cliente, su propio mapa de campos y su propio cursor
    de reanudación.
    """

    factory = cast(
        "Callable[[str | None], SyncService] | None",
        getattr(request.app.state, "sync_service_factory", None),
    )
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La sincronización no está configurada.",
        )
    return factory


RepositoryDep = Annotated[OpportunityRepository, Depends(get_repository)]
SyncFactoryDep = Annotated[Callable[[str | None], SyncService], Depends(get_sync_service_factory)]


@router.get(
    "/sources",
    response_model=SourceCoverageResponse,
    summary="Consultar las fuentes y su cobertura declarada",
)
def list_sources(
    repository: RepositoryDep,
    principal: CurrentPrincipal,
) -> SourceCoverageResponse:
    """Qué fuentes existen, cuáles se sincronizan y cuántas filas aporta cada una.

    Existe para que la interfaz pueda declarar la cobertura con datos en lugar
    de con una frase fija. Si SECOP I solo está parcialmente cubierto, el
    analista tiene que poder verlo: lo contrario es dejarle creer que el
    listado contiene todo el mercado público.
    """

    del principal  # La identidad ya quedó resuelta por la dependencia.
    counts = {dataset: total for dataset, _platform, total in repository.source_counts()}

    return SourceCoverageResponse(
        sources=[
            SourceCoverage(
                dataset=source.dataset,
                platform=source.platform,
                label=source.label,
                short_label=source.short_label,
                coverage=source.coverage,
                note=source.coverage_note,
                opportunity_count=counts.get(source.dataset, 0),
                amount_label=source.amount_label,
            )
            for source in SOURCES
        ]
    )


@router.get(
    "/opportunities",
    response_model=OpportunityPage,
    summary="Listar oportunidades sincronizadas",
)
def list_opportunities(
    repository: RepositoryDep,
    principal: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    source: Annotated[
        str | None,
        Query(description="Conjunto de datos de origen, p. ej. p6dx-8zbt"),
    ] = None,
    platform: Annotated[
        str | None,
        Query(description="Plataforma de origen: SECOP_I o SECOP_II"),
    ] = None,
    entity_nit: Annotated[str | None, Query(description="NIT de la entidad, solo dígitos")] = None,
    estado: Annotated[str | None, Query(description="Estado del proceso")] = None,
    modalidad: Annotated[str | None, Query(description="Modalidad de contratación")] = None,
    desde: Annotated[
        datetime | None,
        Query(description="Publicadas en o después de esta fecha (ISO 8601)"),
    ] = None,
    hasta: Annotated[
        datetime | None,
        Query(description="Publicadas en o antes de esta fecha (ISO 8601)"),
    ] = None,
    q: Annotated[
        str | None,
        Query(description="Búsqueda libre en referencia, título y entidad"),
    ] = None,
) -> OpportunityPage:
    """Devuelve las oportunidades filtradas, de la más reciente a la más antigua.

    Las filas sin fecha de publicación se ordenan al final: mostrarlas primero
    daría a entender que son lo más reciente.

    Un filtro de fuente desconocido se rechaza con 400 en vez de devolver una
    lista vacía, porque «no hay resultados» y «pediste una fuente que no
    existe» son situaciones distintas y confundirlas oculta un error.
    """

    del principal  # La identidad ya quedó resuelta por la dependencia.

    if source is not None:
        try:
            get_source(source)
        except UnknownSourceError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
            ) from error

    if desde is not None and hasta is not None and desde > hasta:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El rango de fechas está invertido: `desde` es posterior a `hasta`.",
        )

    filters = OpportunityFilters(
        source_dataset=source,
        platform=platform,
        entity_nit=entity_nit,
        status=estado,
        modality=modalidad,
        published_from=desde,
        published_to=hasta,
        search=q,
    )

    items = repository.list_filtered(filters=filters, limit=limit, offset=offset)

    # Se consultan solo los grupos de esta página: hacerlo sobre toda la tabla
    # crecería sin límite y no aportaría nada a lo que se está mostrando.
    platforms_by_group = repository.platforms_by_group(
        [item.group_key for item in items if item.group_key]
    )

    return OpportunityPage(
        items=[
            OpportunitySummary.from_opportunity(
                item,
                duplicate_platforms=platforms_by_group.get(item.group_key or "", set()),
            )
            for item in items
        ],
        total=repository.count_filtered(filters),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/opportunities/{opportunity_id}",
    response_model=OpportunitySummary,
    summary="Consultar una oportunidad",
    responses={404: {"description": "La oportunidad no existe"}},
)
def get_opportunity(
    opportunity_id: int,
    repository: RepositoryDep,
    principal: CurrentPrincipal,
) -> OpportunitySummary:
    del principal
    found = repository.get_by_id(opportunity_id)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La oportunidad no existe.",
        )
    duplicates = repository.platforms_by_group([found.group_key] if found.group_key else [])
    return OpportunitySummary.from_opportunity(
        found, duplicate_platforms=duplicates.get(found.group_key or "", set())
    )


@router.post(
    "/sync-runs",
    response_model=SyncTriggerResponse,
    summary="Ejecutar una sincronización manual",
    responses={
        400: {"description": "La fuente indicada no está registrada"},
        503: {"description": "La sincronización no está configurada"},
    },
)
def trigger_sync(
    sync_factory: SyncFactoryDep,
    principal: CurrentPrincipal,
    dataset: Annotated[
        str | None,
        Query(description="Conjunto a sincronizar; por omisión, la fuente principal"),
    ] = None,
    limit: Annotated[int | None, Query(ge=1, le=1000)] = None,
    resume: bool = False,
) -> SyncTriggerResponse:
    """Ejecuta una sincronización acotada y devuelve su resultado.

    Un fallo del proveedor no se devuelve como error HTTP: se responde con el
    resultado de la ejecución para que quede registrado y visible. Ocultarlo
    tras un 500 haría perder el detalle de qué ocurrió y si algo quedó
    sincronizado.
    """

    del principal

    try:
        service = sync_factory(dataset)
    except UnknownSourceError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from error

    outcome = service.run(SyncRequest(limit=limit, resume=resume))
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
    sync_factory: SyncFactoryDep,
    principal: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[SyncRunSummary]:
    """Historial reciente, del más nuevo al más antiguo.

    El historial es común a todas las fuentes: `dataset` en cada fila indica de
    cuál proviene cada ejecución.
    """

    del principal
    runs = sync_factory(None).recent_runs(limit=limit)
    return [SyncRunSummary.model_validate(run) for run in runs]
