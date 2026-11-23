"""Escenarios financieros de una oportunidad autorizada."""

from datetime import datetime
from typing import Annotated, Literal, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError

from app.api.comparison_routes import Inputs, latest, prepare, present
from app.api.document_routes import PRIVATE, DocumentServices, DossierDep, ServicesDep
from app.api.routes import require_eag_administrator, require_eag_member
from app.api.staffing_routes import view as staffing_view
from app.auth import Role
from app.comparison import Comparison
from app.db.margin_models import MarginVersion
from app.db.models import utcnow
from app.documents.service import DocumentError, Dossier, utc
from app.margin import (
    SCHEMA_VERSION,
    Basis,
    Calculation,
    HiringNeed,
    Scenario,
    ScenarioInputs,
    ScenarioReview,
    ScenarioWrite,
    Workspace,
    calculate,
    published_budget,
)
from app.staffing import StaffingPlan

router = APIRouter(
    prefix="/api/v1/opportunities/{opportunity_id}/margin",
    tags=["margen"],
    dependencies=[Depends(require_eag_member)],
)
MAX_SCENARIOS = 12
HISTORY_SIZE = 30


def context(scope: Dossier, tools: DocumentServices) -> tuple[Basis, datetime]:
    inputs = prepare(scope, tools)
    comparison = present(scope, inputs, latest(scope))
    staffing = staffing_view(scope, inputs, comparison)
    return basis_for(scope, inputs, comparison, staffing), inputs.expires_at


def basis_for(
    scope: Dossier, inputs: Inputs, comparison: Comparison, staffing: StaffingPlan,
) -> Basis:
    op = scope.opportunity
    active = staffing.status == "listo"
    periods = [(role.role, span) for role in staffing.roles for span in role.periods]
    return Basis(
        published_budget=published_budget(op.source_dataset, op.raw_payload.get("precio_base")),
        comparison_revision=comparison.revision if active else None,
        comparison_fingerprint=inputs.fingerprint,
        profile_version=inputs.profile_version,
        staffing_revision=(staffing.audit[0].sequence if staffing.audit else 0) if active else None,
        document_versions=inputs.documents,
        hiring_needs=[
            HiringNeed(
                role=role,
                start=span.start.isoformat(),
                end=span.end.isoformat(),
                shortfall_percent=span.shortfall,
            )
            for role, span in periods
            if span.evaluate_staffing and span.shortfall is not None
        ],
        availability_pending=(
            not active
            or not staffing.demands
            or staffing.incomplete
            or any(demand.missing for demand in staffing.demands)
            or any(span.verify_availability for _, span in periods)
        ),
    )


def scoped(scope: Dossier) -> Select[tuple[MarginVersion]]:
    return select(MarginVersion).where(
        MarginVersion.organization_id == scope.organization_id,
        MarginVersion.opportunity_id == scope.opportunity.id,
    )


def versions(scope: Dossier, scenario_id: UUID) -> Select[tuple[MarginVersion]]:
    return scoped(scope).where(MarginVersion.scenario_id == scenario_id)


def current(scope: Dossier, scenario_id: UUID) -> MarginVersion:
    row = scope.session.scalar(
        versions(scope, scenario_id)
        .order_by(
            MarginVersion.version.desc(),
        )
        .limit(1)
    )
    if row is None or utc(row.expires_at) <= utcnow():
        raise DocumentError(404, "escenario_no_disponible")
    return row


def current_scenarios(scope: Dossier) -> list[MarginVersion]:
    maxima = (
        scoped(scope)
        .with_only_columns(
            MarginVersion.scenario_id,
            func.max(MarginVersion.version).label("latest"),
        )
        .group_by(MarginVersion.scenario_id)
        .subquery()
    )
    statement = (
        scoped(scope)
        .join(
            maxima,
            (MarginVersion.scenario_id == maxima.c.scenario_id)
            & (MarginVersion.version == maxima.c.latest),
        )
        .where(MarginVersion.expires_at > utcnow())
        .order_by(MarginVersion.updated_at.desc())
    )
    return list(scope.session.scalars(statement))


def view(row: MarginVersion, context_basis: Basis) -> Scenario:
    basis = Basis.model_validate(row.basis)
    event = cast(Literal["edicion", "revision"], row.event)
    stale = basis != context_basis or row.rules_version != SCHEMA_VERSION
    return Scenario(
        id=row.scenario_id,
        version=row.version,
        actor_id=row.actor_id,
        updated_at=utc(row.updated_at),
        event=event,
        reason=row.reason,
        basis=basis,
        review_status="desactualizado"
        if stale
        else "revisado"
        if event == "revision"
        else "pendiente",
        inputs=ScenarioInputs.model_validate(row.inputs),
        calculation=Calculation.model_validate(row.calculation),
        rules_version=row.rules_version,
    )


def write_inputs(body: ScenarioWrite, basis: Basis) -> ScenarioInputs:
    inputs = ScenarioInputs.model_validate(
        body.model_dump(exclude={"base_version", "reason", "published_amount"})
    )
    if inputs.income_mode == "presupuesto_publicado":
        if not inputs.income.source or len(inputs.income.source) < 5:
            raise DocumentError(422, "justificar_presupuesto_y_moneda")
        if inputs.income.amount is not None:
            raise DocumentError(422, "ingreso_publicado_no_editable")
        if basis.published_budget is None:
            raise DocumentError(422, "presupuesto_publicado_no_disponible")
        if body.published_amount != basis.published_budget.amount:
            raise DocumentError(409, "presupuesto_publicado_cambio")
        inputs.income.amount = basis.published_budget.amount
    return inputs


def append(
    scope: Dossier,
    scenario_id: UUID,
    version: int,
    inputs: ScenarioInputs,
    basis: Basis,
    expires_at: datetime,
    *,
    event: Literal["edicion", "revision"],
    reason: str | None,
) -> Scenario:
    if expires_at <= utcnow():
        raise DocumentError(409, "entradas_vencidas")
    row = MarginVersion(
        organization_id=scope.organization_id,
        opportunity_id=scope.opportunity.id,
        scenario_id=scenario_id,
        version=version,
        actor_id=scope.principal.subject_id,
        updated_at=utcnow(),
        event=event,
        reason=reason,
        inputs=inputs.model_dump(mode="json"),
        basis=basis.model_dump(mode="json"),
        calculation=calculate(inputs).model_dump(mode="json"),
        rules_version=SCHEMA_VERSION,
        expires_at=expires_at,
    )
    scope.session.add(row)
    try:
        scope.session.commit()
    except IntegrityError:
        scope.session.rollback()
        raise DocumentError(409, "escenario_desactualizado") from None
    return view(row, basis)


@router.get("", response_model=Workspace)
def workspace(scope: DossierDep, tools: ServicesDep, response: Response) -> Workspace:
    basis, _ = context(scope, tools)
    response.headers["Cache-Control"] = PRIVATE
    return Workspace(
        basis=basis,
        scenarios=[view(row, basis) for row in current_scenarios(scope)],
        max_scenarios=MAX_SCENARIOS,
        can_review=scope.principal.membership.role == Role.ADMINISTRATOR,
    )


@router.post("", status_code=201, response_model=Scenario)
def create(
    body: ScenarioWrite,
    scope: DossierDep,
    tools: ServicesDep,
    response: Response,
) -> Scenario:
    scope.lock()
    if body.base_version != 0:
        raise DocumentError(409, "escenario_desactualizado")
    if len(current_scenarios(scope)) >= MAX_SCENARIOS:
        raise DocumentError(409, "limite_escenarios")
    basis, expires_at = context(scope, tools)
    response.headers["Cache-Control"] = PRIVATE
    return append(
        scope,
        uuid4(),
        1,
        write_inputs(body, basis),
        basis,
        expires_at,
        event="edicion",
        reason=body.reason,
    )


@router.put("/{scenario_id}", response_model=Scenario)
def update(
    scenario_id: UUID,
    body: ScenarioWrite,
    scope: DossierDep,
    tools: ServicesDep,
    response: Response,
) -> Scenario:
    scope.lock()
    row = current(scope, scenario_id)
    if row.version != body.base_version:
        raise DocumentError(409, "escenario_desactualizado")
    basis, expires_at = context(scope, tools)
    response.headers["Cache-Control"] = PRIVATE
    return append(
        scope,
        scenario_id,
        row.version + 1,
        write_inputs(body, basis),
        basis,
        expires_at,
        event="edicion",
        reason=body.reason,
    )


@router.get("/{scenario_id}/versions", response_model=list[Scenario])
def history(
    scenario_id: UUID,
    scope: DossierDep,
    tools: ServicesDep,
    response: Response,
    before: Annotated[int | None, Query(ge=1, le=2_147_483_647)] = None,
) -> list[Scenario]:
    current(scope, scenario_id)
    basis, _ = context(scope, tools)
    statement = versions(scope, scenario_id).where(MarginVersion.expires_at > utcnow())
    if before is not None:
        statement = statement.where(MarginVersion.version < before)
    response.headers["Cache-Control"] = PRIVATE
    return [
        view(row, basis)
        for row in scope.session.scalars(
            statement.order_by(MarginVersion.version.desc()).limit(HISTORY_SIZE)
        )
    ]


@router.get("/{scenario_id}/versions/{version}", response_model=Scenario)
def snapshot(
    scenario_id: UUID,
    version: Annotated[int, Path(ge=1, le=2_147_483_647)],
    scope: DossierDep,
    tools: ServicesDep,
    response: Response,
) -> Scenario:
    row = scope.session.scalar(versions(scope, scenario_id).where(MarginVersion.version == version))
    if row is None or utc(row.expires_at) <= utcnow():
        raise DocumentError(404, "escenario_no_disponible")
    basis, _ = context(scope, tools)
    response.headers["Cache-Control"] = PRIVATE
    return view(row, basis)


@router.post(
    "/{scenario_id}/review",
    response_model=Scenario,
    dependencies=[Depends(require_eag_administrator)],
)
def review(
    scenario_id: UUID,
    body: ScenarioReview,
    scope: DossierDep,
    tools: ServicesDep,
    response: Response,
) -> Scenario:
    scope.lock()
    row = current(scope, scenario_id)
    basis, expires_at = context(scope, tools)
    scenario = view(row, basis)
    if row.version != body.base_version or scenario.review_status == "desactualizado":
        raise DocumentError(409, "escenario_desactualizado")
    if scenario.calculation.missing_amounts or scenario.calculation.missing_sources:
        raise DocumentError(409, "supuestos_pendientes")
    response.headers["Cache-Control"] = PRIVATE
    if scenario.review_status == "revisado":
        return scenario
    return append(
        scope,
        scenario_id,
        row.version + 1,
        scenario.inputs,
        basis,
        min(expires_at, utc(row.expires_at)),
        event="revision",
        reason=body.reason,
    )
