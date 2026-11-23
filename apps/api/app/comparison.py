"""Reglas explicables para contrastar evidencia versionada."""

import re
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.documents.requirements import Analysis, Citation, Finding, folded
from app.profile import Entry, EvidenceReference

RULE_VERSION = "1"
Outcome = Literal["cumple", "cumple_parcialmente", "no_cumple", "revision_manual"]
Decision = Literal["generado", "corregido", "aprobado"]
NUMBER = re.compile(r"(minimo|maximo) (\d{1,12}(?:[,.]\d{1,2})?) ([a-z%]+)")
DATE = re.compile(r"vigente al (\d{4}-\d{2}-\d{2})")
UNITS: dict[str, tuple[str, int]] = {
    "mes": ("mes", 1),
    "meses": ("mes", 1),
    "ano": ("mes", 12),
    "anos": ("mes", 12),
    "cop": ("cop", 1),
    "usd": ("usd", 1),
    "eur": ("eur", 1),
    "unidad": ("unidad", 1),
    "unidades": ("unidad", 1),
    "%": ("%", 1),
}


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProfileSource(Contract):
    index: int
    title: str
    evidence: list[EvidenceReference]


class Row(Contract):
    id: str
    kind: Literal["habilitante", "evaluable", "obligacion"]
    citation: Citation
    outcome: Outcome
    reason: str
    profile_sources: list[ProfileSource]
    corrected: bool = False


class Correction(Contract):
    outcome: Outcome
    reason: str = Field(min_length=5, max_length=500)
    profile_entry: int | None = Field(default=None, ge=0, le=149)


class RevisionRequest(Contract):
    revision: int = Field(ge=1, le=2_147_483_646)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class CorrectionRequest(RevisionRequest, Correction):
    row_id: str = Field(pattern=r"^[0-9a-f]{64}$")


class ApprovalRequest(RevisionRequest):
    reason: str = Field(min_length=5, max_length=500)


class DocumentBasis(Contract):
    id: UUID
    version: int
    sha256: str


class Audit(Contract):
    revision: int
    action: Decision
    actor_id: UUID
    actor_role: str
    created_at: datetime
    profile_version: int
    document_versions: list[DocumentBasis]
    fingerprint: str
    row_id: str | None = None
    before: Outcome | None = None
    after: Outcome | None = None
    reason: str | None = None
    outcomes: dict[str, Outcome] | None = None


class Comparison(Contract):
    revision: int
    fingerprint: str
    profile_version: int
    status: Literal["sin_generar", "borrador", "aprobado", "invalidado"]
    invalidated_by: list[str]
    incomplete: bool
    warnings: list[str]
    rows: list[Row]
    profile_options: list[ProfileSource]
    audit: list[Audit]


def evaluate_value(
    clause: str,
    entry: Entry,
    as_of: date | None,
) -> tuple[Outcome, str]:
    numeric = NUMBER.fullmatch(clause)
    validity = DATE.fullmatch(clause)
    if validity:
        try:
            as_of = date.fromisoformat(validity[1])
        except ValueError:
            return "revision_manual", "La fecha del requisito es ambigua."
    if validity or entry.starts_on or entry.ends_on:
        if as_of is None or entry.starts_on is None or entry.ends_on is None:
            return "revision_manual", "Faltan fechas para contrastar la vigencia."
        if not entry.starts_on <= as_of <= entry.ends_on:
            return (
                "no_cumple",
                "La evidencia registrada está fuera de vigencia en la fecha exigida.",
            )
    if validity:
        return "cumple", "La fecha exigida está dentro del periodo verificado."
    if numeric and entry.amount is not None and entry.unit:
        required_unit = UNITS.get(numeric[3])
        profile_unit = UNITS.get(folded(entry.unit))
        if not required_unit or not profile_unit or required_unit[0] != profile_unit[0]:
            return "revision_manual", "La unidad o moneda no es comparable."
        expected = Decimal(numeric[2].replace(",", ".")) * required_unit[1]
        observed = entry.amount * profile_unit[1]
        ok = observed >= expected if numeric[1] == "minimo" else observed <= expected
        reason = (
            "El valor verificado satisface el umbral." if ok else "El valor queda fuera del umbral."
        )
        return ("cumple" if ok else "no_cumple"), reason
    return "revision_manual", "El requisito o sus valores requieren contraste humano."


def source_for(index: int, entry: Entry) -> ProfileSource:
    return ProfileSource(index=index, title=entry.title, evidence=entry.evidence)


def row_for(
    finding: Finding,
    entries: list[Entry],
    as_of: date | None,
    conflicted: set[tuple[UUID, str]],
) -> Row:
    assert finding.kind in {"habilitante", "evaluable", "obligacion"}
    quote = finding.citation.quote
    parts = quote.split(":", 2)
    subject = parts[1] if len(parts) == 3 else ""
    clause = folded(parts[2].strip().rstrip(".")) if len(parts) == 3 else ""
    matches = [
        (i, entry)
        for i, entry in enumerate(entries)
        if subject and folded(entry.title) == folded(subject.strip())
    ]
    choices = [source_for(i, entry) for i, entry in matches]
    eligible = [entry for _, entry in matches if entry.status == "verificado" and entry.evidence]
    outcome: Outcome = "revision_manual"
    if (finding.citation.document_id, quote) in conflicted:
        reason = "Hay una posible contradicción entre el pliego y sus adendas."
    elif not eligible:
        reason = "Falta evidencia empresarial verificada para el requisito."
    elif len(eligible) != 1:
        reason = "Hay varias evidencias empresariales posibles. Confirma cuál corresponde."
    elif finding.kind == "evaluable":
        reason = "El criterio evaluable requiere revisar la regla de puntuación."
    else:
        outcome, reason = evaluate_value(clause, eligible[0], as_of)
    return Row(
        id=sha256(finding.model_dump_json().encode()).hexdigest(),
        kind=finding.kind,
        citation=finding.citation,
        outcome=outcome,
        reason=reason,
        profile_sources=choices,
    )


def rows_for(analysis: Analysis, entries: list[Entry], as_of: date | None) -> list[Row]:
    conflicts = {
        (cite.document_id, cite.quote)
        for warning in analysis.warnings
        if warning.code == "posible_contradiccion_adenda"
        for cite in warning.citations
    }
    return [row_for(finding, entries, as_of, conflicts) for finding in analysis.requirements]
