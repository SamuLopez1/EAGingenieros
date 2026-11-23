"""Lista corta autorizada y comparación sin mutar otras fichas."""

from typing import cast

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.api.comparison_routes import latest, prepare, present
from app.api.document_routes import PRIVATE, DocumentServices, ServicesDep
from app.api.filter_routes import Database
from app.api.margin_routes import basis_for, current_scenarios
from app.api.margin_routes import view as margin_view
from app.api.routes import EagMember, require_eag_member
from app.api.staffing_routes import view as staffing_view
from app.config import Settings
from app.db.models import Opportunity
from app.db.shortlist_models import OpportunityShortlist
from app.documents.service import DocumentError, Dossier, utc
from app.shortlist import (
    Column,
    ComparisonTable,
    SavedOpportunity,
    Shortlist,
    ShortlistWrite,
    select_gaps,
    select_margin,
    select_personnel,
)

router = APIRouter(
    prefix="/api/v1/opportunity-shortlist",
    tags=["lista corta"],
    dependencies=[Depends(require_eag_member)],
)


def current(member: EagMember, session: Database) -> OpportunityShortlist | None:
    return session.get(OpportunityShortlist, (member.membership.organization_id, member.subject_id))


def get_opportunities(session: Database, ids: list[int]) -> dict[int, Opportunity]:
    if not ids:
        return {}
    return {
        opportunity.id: opportunity
        for opportunity in session.scalars(select(Opportunity).where(Opportunity.id.in_(ids)))
    }


def label(opportunity_id: int, opportunity: Opportunity | None) -> SavedOpportunity:
    return SavedOpportunity(
        id=opportunity_id,
        title=opportunity.title if opportunity else None,
        reference=opportunity.reference if opportunity else None,
        available=opportunity is not None,
    )


def view(row: OpportunityShortlist | None, session: Database) -> Shortlist:
    if row is None:
        return Shortlist(revision=0, items=[])
    opportunities = get_opportunities(session, row.opportunity_ids)
    return Shortlist(
        revision=row.revision,
        items=[label(op, opportunities.get(op)) for op in row.opportunity_ids],
    )


@router.get("", response_model=Shortlist)
def read(member: EagMember, session: Database, response: Response) -> Shortlist:
    response.headers["Cache-Control"] = PRIVATE
    return view(current(member, session), session)


@router.put("", response_model=Shortlist)
def save(
    body: ShortlistWrite, member: EagMember, session: Database, response: Response
) -> Shortlist:
    response.headers["Cache-Control"] = PRIVATE
    row = current(member, session)
    version = row.revision if row else 0
    if version != body.revision:
        raise DocumentError(409, "lista_desactualizada")
    previous = row.opportunity_ids if row else []
    additional = [value for value in body.opportunity_ids if value not in previous]
    if len(get_opportunities(session, additional)) != len(additional):
        raise DocumentError(404, "oportunidad_no_encontrada")
    if previous == body.opportunity_ids:
        return view(row, session)
    if row is None:
        row = OpportunityShortlist(
            organization_id=member.membership.organization_id,
            subject_id=member.subject_id,
            revision=1,
            opportunity_ids=body.opportunity_ids,
        )
        session.add(row)
    else:
        saved = session.scalar(
            update(OpportunityShortlist)
            .where(
                OpportunityShortlist.organization_id == member.membership.organization_id,
                OpportunityShortlist.subject_id == member.subject_id,
                OpportunityShortlist.revision == version,
            )
            .values(revision=version + 1, opportunity_ids=body.opportunity_ids)
            .returning(OpportunityShortlist.revision),
        )
        if saved is None:
            raise DocumentError(409, "lista_desactualizada")
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise DocumentError(409, "lista_desactualizada") from None
    return view(row, session)


def column(scope: Dossier, tools: DocumentServices) -> Column:
    inputs = prepare(scope, tools)
    comparison = present(scope, inputs, latest(scope))
    staffing = staffing_view(scope, inputs, comparison)
    basis = basis_for(scope, inputs, comparison, staffing)
    opportunity = scope.opportunity
    return Column(
        opportunity=label(opportunity.id, opportunity),
        reception_at=utc(opportunity.reception_at) if opportunity.reception_at else None,
        deadlines=[item.citation for item in inputs.requirements.summary if item.kind == "plazo"],
        published_budget=basis.published_budget,
        gaps=select_gaps(comparison),
        personnel=select_personnel(staffing, basis.availability_pending),
        margins=[select_margin(margin_view(row, basis)) for row in current_scenarios(scope)],
    )


@router.get("/comparison", response_model=ComparisonTable)
def compare(
    request: Request,
    member: EagMember,
    session: Database,
    tools: ServicesDep,
    response: Response,
) -> ComparisonTable:
    row = current(member, session)
    if row is None or len(row.opportunity_ids) < 2:
        raise DocumentError(409, "selecciona_al_menos_dos")
    settings = cast(Settings, request.app.state.opportunity_settings)
    opportunities = get_opportunities(session, row.opportunity_ids)
    response.headers["Cache-Control"] = PRIVATE
    return ComparisonTable(
        revision=row.revision,
        columns=[
            column(Dossier(session, opportunities[op], member, settings), tools)
            if op in opportunities
            else Column(opportunity=label(op, None))
            for op in row.opportunity_ids
        ],
    )
