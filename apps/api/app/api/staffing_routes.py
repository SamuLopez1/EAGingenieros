"""Planificación agregada y revisión humana de los datos de personal."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError

from app.api.comparison_routes import Inputs, latest, prepare, present, require_current
from app.api.document_routes import PRIVATE, DossierDep, ServicesDep
from app.api.routes import require_eag_administrator, require_eag_member
from app.auth import Role
from app.comparison import Comparison
from app.db.models import utcnow
from app.db.staffing_models import StaffingCorrection
from app.documents.service import DocumentError, Dossier, utc
from app.staffing import (
    ROLE,
    CorrectionRequest,
    DemandFields,
    QualifyingGap,
    StaffingAudit,
    StaffingPlan,
    demand_for,
    fit_for,
    normalized,
    plans_for,
)

router = APIRouter(
    prefix="/api/v1/opportunities/{opportunity_id}/staffing",
    tags=["encaje y personal"],
    dependencies=[Depends(require_eag_member)],
)
MAX_CORRECTIONS = 1_000


def history(scope: Dossier, fingerprint: str) -> Select[tuple[StaffingCorrection]]:
    return (
        select(StaffingCorrection)
        .where(
            StaffingCorrection.organization_id == scope.organization_id,
            StaffingCorrection.opportunity_id == scope.opportunity.id,
            StaffingCorrection.fingerprint == fingerprint,
        )
        .order_by(StaffingCorrection.sequence)
    )


def conflicts_for(inputs: Inputs) -> set[tuple[UUID, str]]:
    result: set[tuple[UUID, str]] = set()
    for warning in inputs.requirements.warnings:
        if warning.code != "posible_contradiccion_adenda":
            continue
        roles = {
            normalized(match[1]) for cite in warning.citations if (match := ROLE.search(cite.quote))
        }
        if len(roles) <= 1:
            result.update((cite.document_id, cite.quote) for cite in warning.citations)
    return result


def fields_of(item: DemandFields | None) -> dict[str, object]:
    return item.model_dump(mode="json", include=set(DemandFields.model_fields)) if item else {}


def view(scope: Dossier, inputs: Inputs, comparison: Comparison) -> StaffingPlan:
    active = comparison.status in {"borrador", "aprobado"}
    result = StaffingPlan(
        status="listo" if active else "comparacion_pendiente",
        profile_version=inputs.profile_version,
        comparison_revision=comparison.revision,
        fingerprint=inputs.fingerprint,
        document_versions=inputs.documents,
        incomplete=inputs.requirements.incomplete,
        can_correct=False,
        service_fit=[],
        qualifying_gaps=[],
        demands=[],
        roles=[],
        audit=[],
    )
    if not active:
        return result
    events = list(scope.session.scalars(history(scope, inputs.fingerprint)))
    overrides = {event.row_id: DemandFields.model_validate(event.corrected) for event in events}
    conflicts = conflicts_for(inputs)
    demands = [
        demand
        for row in comparison.rows
        if (demand := demand_for(row, overrides.get(row.id), conflicts)) is not None
    ]
    reception: datetime | None = scope.opportunity.reception_at
    result.service_fit = fit_for(
        inputs.requirements, inputs.entries, reception.date() if reception else None
    )
    result.can_correct = scope.principal.membership.role == Role.ADMINISTRATOR
    result.qualifying_gaps = [
        QualifyingGap(citation=row.citation, outcome=row.outcome, reason=row.reason)
        for row in comparison.rows
        if row.kind == "habilitante" and row.outcome != "cumple"
    ]
    result.demands = demands
    result.roles = plans_for(demands, inputs.entries)
    result.audit = [
        StaffingAudit(
            sequence=event.sequence,
            comparison_revision=event.comparison_revision,
            actor_id=event.actor_id,
            created_at=utc(event.created_at),
            reason=event.reason,
            row_id=event.row_id,
            previous=DemandFields.model_validate(event.previous),
            corrected=DemandFields.model_validate(event.corrected),
        )
        for event in reversed(events)
    ]
    return result


@router.get("", response_model=StaffingPlan)
def read_plan(scope: DossierDep, tools: ServicesDep, response: Response) -> StaffingPlan:
    inputs = prepare(scope, tools)
    response.headers["Cache-Control"] = PRIVATE
    return view(scope, inputs, present(scope, inputs, latest(scope)))


@router.post(
    "/corrections",
    response_model=StaffingPlan,
    dependencies=[Depends(require_eag_administrator)],
)
def correct_plan(
    body: CorrectionRequest,
    scope: DossierDep,
    tools: ServicesDep,
    response: Response,
) -> StaffingPlan:
    scope.lock()
    inputs = prepare(scope, tools)
    last = require_current(inputs, latest(scope), body.revision, body.fingerprint)
    comparison = present(scope, inputs, last)
    row = next((item for item in comparison.rows if item.id == body.row_id), None)
    if row is None:
        raise DocumentError(404, "requisito_no_encontrado")
    events = history(scope, inputs.fingerprint)
    last_event = scope.session.scalar(
        events.order_by(None)
        .order_by(
            StaffingCorrection.sequence.desc(),
        )
        .limit(1)
    )
    sequence = last_event.sequence if last_event else 0
    if body.expected_event != sequence:
        raise DocumentError(409, "plan_desactualizado")
    if sequence >= MAX_CORRECTIONS:
        raise DocumentError(409, "limite_correcciones")
    previous_event = scope.session.scalar(
        events.where(
            StaffingCorrection.row_id == row.id,
        )
        .order_by(None)
        .order_by(StaffingCorrection.sequence.desc())
        .limit(1)
    )
    previous = (
        previous_event.corrected
        if previous_event
        else fields_of(
            demand_for(row, None, conflicts_for(inputs)),
        )
    )
    scope.session.add(
        StaffingCorrection(
            organization_id=scope.organization_id,
            opportunity_id=scope.opportunity.id,
            fingerprint=inputs.fingerprint,
            sequence=sequence + 1,
            comparison_revision=last.revision,
            row_id=row.id,
            actor_id=scope.principal.subject_id,
            created_at=utcnow(),
            reason=body.reason,
            previous=previous,
            corrected=fields_of(body),
        )
    )
    try:
        scope.session.commit()
    except IntegrityError:
        scope.session.rollback()
        raise DocumentError(409, "plan_desactualizado") from None
    response.headers["Cache-Control"] = PRIVATE
    return view(scope, inputs, comparison)
