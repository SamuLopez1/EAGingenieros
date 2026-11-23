"""Estimación decimal a partir de supuestos explícitos."""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, Field, TypeAdapter, ValidationError

from app.comparison import Contract, DocumentBasis
from app.secop.client import PROCESSES_DATASET


def as_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


Money = Annotated[
    Decimal,
    Field(ge=0, max_digits=16, decimal_places=2, allow_inf_nan=False),
    AfterValidator(as_money),
]
Currency = Literal["COP", "USD", "EUR"]
CostName = Literal["direct", "indirect", "internal_staff", "hiring", "contingency"]
COSTS: tuple[CostName, ...] = ("direct", "indirect", "internal_staff", "hiring", "contingency")
AssumptionName = Literal["income", "direct", "indirect", "internal_staff", "hiring", "contingency"]
SCHEMA_VERSION = "1"
money = TypeAdapter(Money)


class Assumption(Contract):
    amount: Money | None = None
    source: str | None = Field(default=None, min_length=1, max_length=400)


class CostInputs(Contract):
    direct: Assumption = Field(default_factory=Assumption)
    indirect: Assumption = Field(default_factory=Assumption)
    internal_staff: Assumption = Field(default_factory=Assumption)
    hiring: Assumption = Field(default_factory=Assumption)
    contingency: Assumption = Field(default_factory=Assumption)


class ScenarioInputs(Contract):
    name: str = Field(min_length=1, max_length=80)
    currency: Currency
    income_mode: Literal["estimado", "presupuesto_publicado"] = "estimado"
    income: Assumption = Field(default_factory=Assumption)
    costs: CostInputs = Field(default_factory=CostInputs)


class ScenarioWrite(ScenarioInputs):
    base_version: int = Field(ge=0, le=2_147_483_646)
    published_amount: Money | None = None
    reason: str | None = Field(default=None, min_length=5, max_length=400)


class ScenarioReview(Contract):
    base_version: int = Field(ge=1, le=2_147_483_646)
    reason: str = Field(min_length=5, max_length=400)


class PublishedBudget(Contract):
    amount: Money
    dataset: str = PROCESSES_DATASET
    field: Literal["precio_base"] = "precio_base"


class HiringNeed(Contract):
    role: str
    start: str
    end: str
    shortfall_percent: Decimal


class Basis(Contract):
    published_budget: PublishedBudget | None
    comparison_revision: int | None
    comparison_fingerprint: str
    profile_version: int
    staffing_revision: int | None
    document_versions: list[DocumentBasis]
    hiring_needs: list[HiringNeed]
    availability_pending: bool


class Calculation(Contract):
    status: Literal["pendiente", "calculado", "ingreso_cero"]
    missing_amounts: list[AssumptionName]
    missing_sources: list[AssumptionName]
    total_cost: Decimal | None
    profit: Decimal | None
    margin_percent: Decimal | None


class Scenario(Contract):
    id: UUID
    version: int
    actor_id: UUID
    updated_at: datetime
    event: Literal["edicion", "revision"]
    reason: str | None
    review_status: Literal["pendiente", "revisado", "desactualizado"]
    inputs: ScenarioInputs
    basis: Basis
    calculation: Calculation
    rules_version: str = SCHEMA_VERSION


class Workspace(Contract):
    basis: Basis
    scenarios: list[Scenario]
    max_scenarios: int
    can_review: bool


def published_budget(dataset: str, value: object) -> PublishedBudget | None:
    if dataset != PROCESSES_DATASET or type(value) not in {str, int, float, Decimal}:
        return None
    try:
        return PublishedBudget(amount=money.validate_python(value))
    except ValidationError:
        return None


def calculate(inputs: ScenarioInputs) -> Calculation:
    entries: list[tuple[AssumptionName, Assumption]] = [
        ("income", inputs.income),
        *((key, getattr(inputs.costs, key)) for key in COSTS),
    ]
    missing_amounts = [key for key, value in entries if value.amount is None]
    missing_sources = [key for key, value in entries if not value.source]
    if missing_amounts:
        return Calculation(
            status="pendiente",
            missing_amounts=missing_amounts,
            missing_sources=missing_sources,
            total_cost=None,
            profit=None,
            margin_percent=None,
        )
    income = inputs.income.amount
    assert income is not None
    total = sum(
        (cost.amount for _, cost in entries[1:] if cost.amount is not None),
        Decimal(0),
    )
    profit = income - total
    with localcontext() as context:
        context.prec = 40
        margin = (
            (profit * 100 / income).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            if income
            else None
        )
    return Calculation(
        status="calculado" if income else "ingreso_cero",
        missing_amounts=[],
        missing_sources=missing_sources,
        total_cost=total,
        profit=profit,
        margin_percent=margin,
    )
