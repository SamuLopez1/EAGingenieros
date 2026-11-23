"""Filtros compartidos: lectura para miembros y escritura solo de administrador."""

from collections.abc import Iterator
from datetime import datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.auth import Principal, Role, get_current_principal, require_roles
from app.catalog import FilterCriteria
from app.db.filter_models import SavedOpportunityFilter
from app.db.models import utcnow

router = APIRouter(prefix="/api/v1/opportunity-filters", tags=["filtros compartidos"])
Member = Annotated[Principal, Depends(get_current_principal)]
Administrator = Annotated[Principal, Depends(require_roles(Role.ADMINISTRATOR))]


def get_session(request: Request) -> Iterator[Session]:
    factory = cast(
        "sessionmaker[Session] | None",
        getattr(request.app.state, "opportunity_session_factory", None),
    )
    if factory is None:
        raise HTTPException(503, "Los filtros compartidos requieren persistencia configurada.")
    with factory() as session:
        yield session


Database = Annotated[Session, Depends(get_session)]


class FilterWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    criteria: FilterCriteria


class FilterView(FilterWrite):
    model_config = ConfigDict(from_attributes=True)
    id: int
    updated_at: datetime


@router.get("", response_model=list[FilterView])
def list_filters(member: Member, session: Database) -> list[SavedOpportunityFilter]:
    return list(
        session.scalars(
            select(SavedOpportunityFilter)
            .where(SavedOpportunityFilter.organization_id == member.membership.organization_id)
            .order_by(SavedOpportunityFilter.name, SavedOpportunityFilter.id)
        )
    )


def commit(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            409, "Ya existe un filtro con ese nombre en esta organización."
        ) from None


@router.post("", response_model=FilterView, status_code=201)
def create_filter(
    administrator: Administrator, body: FilterWrite, session: Database
) -> SavedOpportunityFilter:
    item = SavedOpportunityFilter(
        organization_id=administrator.membership.organization_id,
        name=body.name,
        criteria=body.criteria.model_dump(mode="json"),
    )
    session.add(item)
    commit(session)
    return item


def find(session: Session, member: Principal, filter_id: int) -> SavedOpportunityFilter:
    item = session.scalar(
        select(SavedOpportunityFilter).where(
            SavedOpportunityFilter.id == filter_id,
            SavedOpportunityFilter.organization_id == member.membership.organization_id,
        )
    )
    if item is None:
        raise HTTPException(404, "El filtro no existe.")
    return item


@router.put("/{filter_id}", response_model=FilterView)
def update_filter(
    filter_id: int, administrator: Administrator, body: FilterWrite, session: Database
) -> SavedOpportunityFilter:
    item = find(session, administrator, filter_id)
    item.name, item.criteria = body.name, body.criteria.model_dump(mode="json")
    item.updated_at = utcnow()
    commit(session)
    return item


@router.delete("/{filter_id}", status_code=204)
def delete_filter(filter_id: int, administrator: Administrator, session: Database) -> None:
    session.delete(find(session, administrator, filter_id))
    commit(session)
