"""Matriz privada y revisiones humanas vinculadas a sus entradas."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256

from fastapi import APIRouter, Depends, Response
from pydantic import TypeAdapter
from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError

from app.api.document_routes import PRIVATE, DocumentServices, DossierDep, ServicesDep
from app.api.profile_routes import current as current_profile
from app.api.requirements_routes import analyze_selected
from app.api.routes import require_eag_administrator, require_eag_member
from app.comparison import (
    RULE_VERSION,
    ApprovalRequest,
    Audit,
    Comparison,
    Correction,
    CorrectionRequest,
    Decision,
    DocumentBasis,
    Row,
    rows_for,
    source_for,
)
from app.db.comparison_models import ComparisonRevision, DossierRevision
from app.db.models import utcnow
from app.documents.requirements import Analysis
from app.documents.service import DocumentError, Dossier, utc
from app.profile import Entry

router = APIRouter(
    prefix="/api/v1/opportunities/{opportunity_id}/comparison",
    tags=["comparación EAG"],
    dependencies=[Depends(require_eag_member)],
)
stored_corrections = TypeAdapter(dict[str, Correction])


@dataclass
class Inputs:
    dossier_key: str
    fingerprint: str
    profile_version: int
    documents: list[DocumentBasis]
    entries: list[Entry]
    requirements: Analysis
    rows: list[Row]
    expires_at: datetime


def prepare(scope: Dossier, tools: DocumentServices) -> Inputs:
    epoch = scope.session.get(DossierRevision, (scope.organization_id, scope.opportunity.id))
    profile = current_profile(scope.session, scope.organization_id)
    entries = [Entry.model_validate(entry) for entry in profile.entries] if profile else []
    version = profile.version if profile else 0
    requirements = analyze_selected(scope, tools)
    reception = scope.opportunity.reception_at
    day = reception.date() if reception else None
    dossier_key = sha256(
        f"{epoch.revision if epoch else 0}/{requirements.fingerprint}/{day}".encode()
    ).hexdigest()
    fingerprint = sha256(f"{dossier_key}/{version}/{RULE_VERSION}".encode()).hexdigest()
    now = utcnow()
    selected = [
        doc
        for doc in scope.items()
        if doc.under_review and doc.status == "disponible" and utc(doc.retention_until) > now
    ]
    return Inputs(
        dossier_key=dossier_key,
        fingerprint=fingerprint,
        profile_version=version,
        documents=[
            DocumentBasis(id=doc.id, version=doc.version, sha256=doc.sha256) for doc in selected
        ],
        entries=entries,
        requirements=requirements,
        rows=rows_for(requirements, entries, day),
        expires_at=min(
            (utc(doc.retention_until) for doc in selected),
            default=now + timedelta(days=scope.settings.document_retention_days),
        ),
    )


def events(scope: Dossier) -> Select[tuple[ComparisonRevision]]:
    return select(ComparisonRevision).where(
        ComparisonRevision.organization_id == scope.organization_id,
        ComparisonRevision.opportunity_id == scope.opportunity.id,
    )


def latest(scope: Dossier) -> ComparisonRevision | None:
    return scope.session.scalar(events(scope).order_by(ComparisonRevision.revision.desc()).limit(1))


def apply_corrections(inputs: Inputs, corrections: dict[str, Correction]) -> list[Row]:
    rows = []
    for row in inputs.rows:
        correction = corrections.get(row.id)
        if correction:
            evidence = row.profile_sources
            if correction.profile_entry is not None:
                index = correction.profile_entry
                evidence = [source_for(index, inputs.entries[index])]
            row = row.model_copy(
                update={
                    "outcome": correction.outcome,
                    "reason": correction.reason,
                    "profile_sources": evidence,
                    "corrected": True,
                }
            )
        rows.append(row)
    return rows


def audit_entry(event: ComparisonRevision) -> Audit:
    return Audit.model_validate(
        {
            **event.audit_details,
            "revision": event.revision,
            "action": event.action,
            "actor_id": event.actor_id,
            "actor_role": event.actor_role,
            "created_at": utc(event.created_at),
            "profile_version": event.profile_version,
            "fingerprint": event.fingerprint,
        }
    )


def present(scope: Dossier, inputs: Inputs, last: ComparisonRevision | None) -> Comparison:
    now = utcnow()
    result = Comparison(
        revision=last.revision if last else 0,
        fingerprint=inputs.fingerprint,
        profile_version=inputs.profile_version,
        status="sin_generar",
        invalidated_by=[],
        incomplete=inputs.requirements.incomplete,
        warnings=list(dict.fromkeys(w.code for w in inputs.requirements.warnings)),
        rows=[],
        profile_options=[],
        audit=[],
    )
    if last is None:
        return result
    result.audit = [
        audit_entry(event)
        for event in scope.session.scalars(
            events(scope)
            .where(ComparisonRevision.expires_at > now)
            .order_by(ComparisonRevision.revision.desc())
            .limit(50)
        )
    ]
    if last.dossier_key != inputs.dossier_key:
        result.invalidated_by.append("expediente")
    if last.profile_version != inputs.profile_version:
        result.invalidated_by.append("perfil")
    if utc(last.expires_at) <= now:
        result.invalidated_by.append("retencion")
    if last.fingerprint != inputs.fingerprint and not result.invalidated_by:
        result.invalidated_by.append("reglas")
    if result.invalidated_by:
        result.status = "invalidado"
        return result
    result.status = "aprobado" if last.action == "aprobado" else "borrador"
    result.rows = apply_corrections(inputs, stored_corrections.validate_python(last.corrections))
    result.profile_options = [
        source_for(i, entry)
        for i, entry in enumerate(inputs.entries)
        if entry.status == "verificado" and entry.evidence
    ]
    return result


def append(
    scope: Dossier,
    inputs: Inputs,
    last: ComparisonRevision | None,
    action: Decision,
    corrections: dict[str, Correction],
    details: dict[str, object],
) -> ComparisonRevision:
    event = ComparisonRevision(
        organization_id=scope.organization_id,
        opportunity_id=scope.opportunity.id,
        revision=last.revision + 1 if last else 1,
        actor_id=scope.principal.subject_id,
        actor_role=scope.principal.membership.role.value,
        created_at=utcnow(),
        action=action,
        fingerprint=inputs.fingerprint,
        dossier_key=inputs.dossier_key,
        profile_version=inputs.profile_version,
        expires_at=inputs.expires_at,
        audit_details={
            **details,
            "document_versions": [doc.model_dump(mode="json") for doc in inputs.documents],
        },
        corrections={key: value.model_dump(mode="json") for key, value in corrections.items()},
    )
    scope.session.add(event)
    try:
        scope.session.commit()
    except IntegrityError:
        scope.session.rollback()
        raise DocumentError(409, "revision_desactualizada") from None
    return event


def require_current(
    inputs: Inputs,
    last: ComparisonRevision | None,
    revision: int,
    fingerprint: str,
) -> ComparisonRevision:
    if (
        last is None
        or last.revision != revision
        or last.fingerprint != fingerprint
        or inputs.fingerprint != fingerprint
        or utc(last.expires_at) <= utcnow()
    ):
        raise DocumentError(409, "revision_desactualizada")
    return last


@router.get("", response_model=Comparison)
def read(scope: DossierDep, tools: ServicesDep, response: Response) -> Comparison:
    response.headers["Cache-Control"] = PRIVATE
    last = latest(scope)
    return present(scope, prepare(scope, tools), last)


@router.post("", response_model=Comparison)
def compare(scope: DossierDep, tools: ServicesDep, response: Response) -> Comparison:
    scope.lock()
    inputs = prepare(scope, tools)
    last = latest(scope)
    if last is None or last.fingerprint != inputs.fingerprint or utc(last.expires_at) <= utcnow():
        last = append(scope, inputs, last, "generado", {}, {})
    response.headers["Cache-Control"] = PRIVATE
    return present(scope, inputs, last)


@router.post("/corrections", response_model=Comparison)
def correct(
    body: CorrectionRequest,
    scope: DossierDep,
    tools: ServicesDep,
    response: Response,
) -> Comparison:
    scope.lock()
    inputs = prepare(scope, tools)
    last = require_current(inputs, latest(scope), body.revision, body.fingerprint)
    corrections = stored_corrections.validate_python(last.corrections)
    row = next(
        (item for item in apply_corrections(inputs, corrections) if item.id == body.row_id), None
    )
    if row is None:
        raise DocumentError(404, "requisito_no_encontrado")
    index = body.profile_entry
    if index is not None and (
        index >= len(inputs.entries)
        or inputs.entries[index].status != "verificado"
        or not inputs.entries[index].evidence
    ):
        raise DocumentError(422, "evidencia_empresarial_no_verificada")
    if body.outcome in {"cumple", "cumple_parcialmente"} and index is None:
        raise DocumentError(422, "evidencia_empresarial_requerida")
    corrections[row.id] = Correction(
        outcome=body.outcome,
        reason=body.reason,
        profile_entry=index,
    )
    event = append(
        scope,
        inputs,
        last,
        "corregido",
        corrections,
        {
            "row_id": row.id,
            "before": row.outcome,
            "after": body.outcome,
            "reason": body.reason,
        },
    )
    response.headers["Cache-Control"] = PRIVATE
    return present(scope, inputs, event)


@router.post(
    "/approve", response_model=Comparison, dependencies=[Depends(require_eag_administrator)]
)
def approve(
    body: ApprovalRequest,
    scope: DossierDep,
    tools: ServicesDep,
    response: Response,
) -> Comparison:
    scope.lock()
    inputs = prepare(scope, tools)
    last = require_current(inputs, latest(scope), body.revision, body.fingerprint)
    if not inputs.rows or not inputs.profile_version:
        raise DocumentError(409, "comparacion_sin_requisitos_o_perfil")
    response.headers["Cache-Control"] = PRIVATE
    if last.action == "aprobado":
        return present(scope, inputs, last)
    corrections = stored_corrections.validate_python(last.corrections)
    outcomes = {row.id: row.outcome for row in apply_corrections(inputs, corrections)}
    event = append(
        scope,
        inputs,
        last,
        "aprobado",
        corrections,
        {
            "reason": body.reason,
            "outcomes": outcomes,
        },
    )
    return present(scope, inputs, event)
