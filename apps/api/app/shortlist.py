"""Proyección acotada de las fichas comparadas."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, field_validator

from app.comparison import Comparison, Contract, Outcome
from app.documents.requirements import Citation
from app.margin import AssumptionName, Currency, PublishedBudget, Scenario
from app.staffing import StaffingPlan

LIMIT = 3
OpportunityId = Annotated[int, Field(strict=True, gt=0, le=9_007_199_254_740_991)]


class ShortlistWrite(Contract):
    revision: int = Field(ge=0, le=2_147_483_646)
    opportunity_ids: list[OpportunityId] = Field(max_length=LIMIT)

    @field_validator("opportunity_ids")
    @classmethod
    def distinct(cls, values: list[int]) -> list[int]:
        if len(set(values)) != len(values):
            raise ValueError("Cada oportunidad debe aparecer una sola vez.")
        return values


class SavedOpportunity(Contract):
    id: int
    title: str | None = None
    reference: str | None = None
    available: bool


class Shortlist(Contract):
    revision: int
    items: list[SavedOpportunity]


class Gap(Contract):
    kind: Literal["habilitante", "evaluable", "obligacion"]
    outcome: Outcome
    reason: str
    citation: Citation


class Gaps(Contract):
    status: Literal["sin_generar", "borrador", "aprobado", "invalidado"]
    revision: int
    incomplete: bool
    assessed: int
    items: list[Gap]


class StaffingGap(Contract):
    start: str
    end: str
    shortfall_percent: Decimal


class StaffingRole(Contract):
    role: str
    confirmed_periods: int
    pending: bool
    gaps: list[StaffingGap]


class Personnel(Contract):
    status: Literal["listo", "comparacion_pendiente"]
    availability_pending: bool
    roles: list[StaffingRole]


class Margin(Contract):
    name: str
    version: int
    currency: Currency
    status: Literal["calculado", "pendiente", "ingreso_cero", "desactualizado"]
    review_status: Literal["revisado", "pendiente", "desactualizado"]
    margin_percent: Decimal | None
    missing_amounts: list[AssumptionName]
    missing_sources: list[AssumptionName]


class Column(Contract):
    opportunity: SavedOpportunity
    reception_at: datetime | None = None
    deadlines: list[Citation] = Field(default_factory=list)
    published_budget: PublishedBudget | None = None
    gaps: Gaps | None = None
    personnel: Personnel | None = None
    margins: list[Margin] = Field(default_factory=list)


class ComparisonTable(Contract):
    revision: int
    columns: list[Column]


def select_gaps(comparison: Comparison) -> Gaps:
    return Gaps(
        status=comparison.status,
        revision=comparison.revision,
        incomplete=comparison.incomplete,
        assessed=len(comparison.rows),
        items=[
            Gap(kind=row.kind, outcome=row.outcome, reason=row.reason, citation=row.citation)
            for row in sorted(comparison.rows, key=lambda row: row.kind != "habilitante")
            if row.outcome != "cumple"
        ],
    )


def select_personnel(staffing: StaffingPlan, availability_pending: bool) -> Personnel:
    pending_roles = {demand.role for demand in staffing.demands if demand.missing}
    return Personnel(
        status=staffing.status,
        availability_pending=availability_pending,
        roles=[
            StaffingRole(
                role=role.role,
                confirmed_periods=sum(p.status == "confirmada" for p in role.periods),
                pending=(
                    not role.periods
                    or role.role in pending_roles
                    or any(span.verify_availability for span in role.periods)
                ),
                gaps=[
                    StaffingGap(
                        start=span.start.isoformat(),
                        end=span.end.isoformat(),
                        shortfall_percent=span.shortfall,
                    )
                    for span in role.periods
                    if span.evaluate_staffing and span.shortfall is not None
                ],
            )
            for role in staffing.roles
        ],
    )


def select_margin(scenario: Scenario) -> Margin:
    result = scenario.calculation
    stale = scenario.review_status == "desactualizado"
    return Margin(
        name=scenario.inputs.name,
        version=scenario.version,
        currency=scenario.inputs.currency,
        status="desactualizado" if stale else result.status,
        review_status=scenario.review_status,
        margin_percent=None if stale else result.margin_percent,
        missing_amounts=[] if stale else result.missing_amounts,
        missing_sources=[] if stale else result.missing_sources,
    )
