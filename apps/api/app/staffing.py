"""Encaje y cobertura de personal basada en requisitos citados."""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from app.comparison import Contract, DocumentBasis, Outcome, RevisionRequest, Row
from app.documents.requirements import Analysis, Citation, folded
from app.profile import Entry, EvidenceReference

Percent = Annotated[Decimal, Field(gt=0, le=10_000, decimal_places=2)]
Coverage = Literal["confirmada", "insuficiente", "por_confirmar"]
ROLE = re.compile(
    r"(?:^|[:;])\s*(?:cargo|personal|perfil)\s*:\s*([^;:,]+)",
    re.I,
)
DEDICATION = re.compile(
    r"(?:^|[;,])\s*dedicacion\s*(?:(?:minima\s+)?d(?:e|el)\s+|:\s*)?(\d{1,5}(?:[.,]\d{1,2})?)\s*%"
)
PERIOD = re.compile(
    r"(?:^|[;,])\s*periodo\s*(?:del\s+|:\s*)?(\d{4}-\d{2}-\d{2})\s+(?:a|al)\s+(\d{4}-\d{2}-\d{2})"
)
SERVICE = re.compile(r"(?:^|[:;])\s*l[ií]nea de servicio\s*:\s*([^;:]+)", re.I)


class DemandFields(Contract):
    role: str | None = Field(default=None, min_length=1, max_length=160)
    dedication: Percent | None = None
    start: date | None = None
    end: date | None = None

    @model_validator(mode="after")
    def period_is_ordered(self) -> Self:
        if self.start and self.end and self.start > self.end:
            raise ValueError("El fin no puede preceder al inicio.")
        return self


class CorrectionRequest(RevisionRequest, DemandFields):
    expected_event: int = Field(ge=0, le=2_147_483_646)
    row_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=5, max_length=500)


class Demand(DemandFields):
    row_id: str
    citation: Citation
    missing: list[str]
    corrected: bool


class Slice(Contract):
    start: date
    end: date
    required: Decimal
    recorded: Decimal | None
    shortfall: Decimal | None
    status: Coverage
    reason: str
    evaluate_staffing: bool
    verify_availability: bool
    demand_ids: list[str]
    evidence: list[EvidenceReference]


class RolePlan(Contract):
    role: str
    periods: list[Slice]


class ServiceSupport(Contract):
    title: str
    category: Literal["experiencia", "capacidad"]
    evidence: list[EvidenceReference]


class ServiceFit(Contract):
    line: str | None
    status: Literal["respaldado", "por_confirmar"]
    reason: str
    citations: list[Citation]
    support: list[ServiceSupport]


class QualifyingGap(Contract):
    citation: Citation
    outcome: Outcome
    reason: str


class StaffingAudit(Contract):
    sequence: int
    comparison_revision: int
    actor_id: UUID
    created_at: datetime
    reason: str
    row_id: str
    previous: DemandFields
    corrected: DemandFields


class StaffingPlan(Contract):
    rules_version: str = "1"
    status: Literal["listo", "comparacion_pendiente"]
    profile_version: int
    comparison_revision: int
    fingerprint: str
    document_versions: list[DocumentBasis]
    suggestions_only: bool = True
    incomplete: bool
    can_correct: bool
    service_fit: list[ServiceFit]
    qualifying_gaps: list[QualifyingGap]
    demands: list[Demand]
    roles: list[RolePlan]
    audit: list[StaffingAudit]


def normalized(text: str) -> str:
    return " ".join(folded(text).split())


def parse_dates(match: re.Match[str] | None) -> tuple[date | None, date | None]:
    if match:
        try:
            first, last = date.fromisoformat(match[1]), date.fromisoformat(match[2])
            if first <= last:
                return first, last
        except ValueError:
            pass
    return None, None


def demand_for(
    row: Row,
    correction: DemandFields | None,
    conflicts: set[tuple[UUID, str]],
) -> Demand | None:
    raw = row.citation.quote
    text = normalized(raw.rstrip("."))
    role = ROLE.search(raw.rstrip("."))
    tagged = role or re.search(r"(?:^|[:;])\s*(?:cargo|personal|perfil)\s*:", text)
    if correction is None and not tagged and "dedicacion:" not in text:
        return None
    fields = correction
    if fields is None:
        percent = DEDICATION.search(text)
        dedication = Decimal(percent[1].replace(",", ".")) if percent else None
        start, end = parse_dates(PERIOD.search(text))
        fields = DemandFields(
            role=role[1].strip()[:160] if role and role[1].strip() else None,
            dedication=dedication if dedication and dedication <= 10_000 else None,
            start=start,
            end=end,
        )
    missing = [
        name
        for name, value in (
            ("cargo", fields.role),
            ("dedicación", fields.dedication),
            ("inicio", fields.start),
            ("fin", fields.end),
        )
        if value is None
    ]
    if (row.citation.document_id, raw) in conflicts:
        missing.append("resolver contradicción entre documentos")
    return Demand(
        **fields.model_dump(),
        row_id=row.id,
        citation=row.citation,
        missing=missing,
        corrected=correction is not None,
    )


def fit_for(analysis: Analysis, entries: list[Entry], as_of: date | None) -> list[ServiceFit]:
    profile = [
        entry
        for entry in entries
        if entry.category in {"capacidad", "experiencia"} and entry.service_line
    ]
    sources = [item.citation for item in (*analysis.summary, *analysis.requirements)]
    lines: dict[str, tuple[str, list[Citation]]] = {}
    for citation in sources:
        explicit = SERVICE.search(citation.quote.rstrip("."))
        if explicit and explicit[1].strip():
            name = explicit[1].strip()[:160]
            lines.setdefault(normalized(name), (name, []))[1].append(citation)
            continue
        text = normalized(citation.quote)
        for name in sorted({entry.service_line for entry in profile if entry.service_line}):
            key = normalized(name)
            if re.search(rf"(?<!\w){re.escape(key)}(?!\w)", text):
                group = lines.setdefault(key, (name, []))[1]
                if citation not in group:
                    group.append(citation)
    fits = []
    for key, (name, evidence) in sorted(lines.items()):
        support = [
            ServiceSupport(title=entry.title, category=entry.category, evidence=entry.evidence)
            for entry in profile
            if entry.category in {"capacidad", "experiencia"}
            and entry.service_line
            and normalized(entry.service_line) == key
            and entry.status == "verificado"
            and entry.evidence
            and (
                (entry.starts_on is None and entry.ends_on is None)
                or (
                    as_of is not None
                    and entry.starts_on is not None
                    and entry.ends_on is not None
                    and entry.starts_on <= as_of <= entry.ends_on
                )
            )
        ]
        fits.append(
            ServiceFit(
                line=name,
                status="respaldado" if support else "por_confirmar",
                reason="La línea tiene experiencia o capacidad respaldada en el perfil."
                if support
                else "Falta evidencia verificada y vigente para esta línea.",
                citations=evidence,
                support=support,
            )
        )
    return fits or [
        ServiceFit(
            line=None,
            status="por_confirmar",
            reason="Confirma la línea de servicio con el objeto y el alcance del expediente.",
            citations=[item.citation for item in analysis.summary if item.kind == "objeto"],
            support=[],
        )
    ]


def overlaps(entry: Entry, start: date, end: date) -> bool:
    return (entry.starts_on is None or entry.starts_on <= end) and (
        entry.ends_on is None or entry.ends_on >= start
    )


def slice_for(
    start: date,
    end: date,
    demand: list[Demand],
    availability: list[Entry],
    uncertain: bool,
) -> Slice:
    required = sum(
        (item.dedication for item in demand if item.dedication is not None),
        Decimal(0),
    )
    verified = [
        item
        for item in availability
        if item.status == "verificado"
        and item.evidence
        and item.dedication_percent is not None
        and item.starts_on is not None
        and item.ends_on is not None
        and item.starts_on <= start
        and item.ends_on >= end
    ]
    values = {item.dedication_percent for item in verified if item.dedication_percent is not None}
    pending = [
        item for item in availability if item.status == "pendiente" and overlaps(item, start, end)
    ]
    confirmed = min(values) if values else None
    shortfall = max(required - confirmed, Decimal(0)) if confirmed is not None else None
    verify = (
        uncertain or confirmed is None or len(values) > 1 or (bool(pending) and bool(shortfall))
    )
    staff = bool(shortfall)
    status: Coverage = "por_confirmar" if verify else "insuficiente" if staff else "confirmada"
    if uncertain:
        reason = "Hay una exigencia adicional o contradictoria por confirmar para este cargo."
    elif confirmed is None:
        reason = "Falta disponibilidad verificada para estas fechas."
    elif len(values) > 1:
        reason = "Los registros de disponibilidad superpuestos requieren conciliación."
    elif pending and staff:
        reason = "La cobertura verificada es insuficiente y hay disponibilidad por confirmar."
    elif staff:
        reason = (
            "Las exigencias simultáneas superan la capacidad registrada."
            if len(demand) > 1
            else ("La dedicación exigida supera la capacidad registrada.")
        )
    else:
        reason = "La disponibilidad verificada cubre la dedicación exigida en este periodo."
    refs = {
        (ref.document_id, ref.locator): ref
        for entry in (*verified, *pending)
        for ref in entry.evidence
    }
    return Slice(
        start=start,
        end=end,
        required=required,
        recorded=confirmed,
        shortfall=shortfall,
        status=status,
        reason=reason,
        evaluate_staffing=staff,
        verify_availability=verify or bool(pending),
        demand_ids=[item.row_id for item in demand],
        evidence=list(refs.values()),
    )


def plans_for(demands: list[Demand], entries: list[Entry]) -> list[RolePlan]:
    roles = sorted({normalized(item.role) for item in demands if item.role})
    plans = []
    for role in roles:
        related = [item for item in demands if item.role and normalized(item.role) == role]
        availability = [
            entry
            for entry in entries
            if entry.category == "disponibilidad" and entry.role and normalized(entry.role) == role
        ]
        # Citas repetidas del mismo requisito comparten una exigencia.
        distinct = {
            (normalized(item.citation.quote), item.dedication, item.start, item.end): item
            for item in related
            if not item.missing
        }
        complete = list(distinct.values())
        edges: set[int] = set()
        intervals = [
            *((item.start, item.end) for item in complete),
            *((entry.starts_on, entry.ends_on) for entry in availability),
        ]
        for first, last in intervals:
            if first:
                edges.add(first.toordinal())
            if last:
                edges.add(last.toordinal() + 1)
        boundaries = sorted(edges)
        periods = []
        for left, right in zip(boundaries, boundaries[1:], strict=False):
            start, end = date.fromordinal(left), date.fromordinal(right - 1)
            active = [
                item
                for item in complete
                if item.start is not None
                and item.end is not None
                and item.start <= start
                and item.end >= end
            ]
            if active:
                uncertain = any(
                    item.missing
                    and (item.start is None or item.start <= end)
                    and (item.end is None or item.end >= start)
                    for item in related
                )
                periods.append(slice_for(start, end, active, availability, uncertain))
        label = next(item.role for item in related if item.role)
        plans.append(RolePlan(role=label, periods=periods))
    return plans
