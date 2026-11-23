"""Consultas del catálogo: filtros sobre todo el conjunto, con orden estable."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Opportunity, SyncRun
from app.opportunity_fields import CLOSED, OFFER_PHASE, OFFERING, Validity, validity
from app.secop.client import PROCESSES_DATASET

Sort = Literal["published_desc", "published_asc", "entity_asc", "title_asc", "synced_desc"]


class FilterCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    q: str = Field(default="", max_length=200)
    entity: str = Field(default="", max_length=200)
    location: str = Field(default="", max_length=200)
    status: str = Field(default="", max_length=128)
    validity: Validity | None = None
    closing_from: date | None = None
    closing_to: date | None = Field(default=None, le=date(9999, 12, 30))
    modality: str = Field(default="", max_length=200)
    published_from: date | None = None
    published_to: date | None = Field(default=None, le=date(9999, 12, 30))
    sort: Sort = "published_desc"

    @model_validator(mode="after")
    def valid_range(self) -> Self:
        periods = (
            (self.published_from, self.published_to),
            (self.closing_from, self.closing_to),
        )
        if any(start and end and start > end for start, end in periods):
            raise ValueError("la fecha inicial no puede ser posterior a la final")
        return self


class CatalogQuery(FilterCriteria):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=1_000_000)


@dataclass
class CatalogResult:
    items: Sequence[Opportunity]
    total: int
    catalog_synced_at: datetime | None
    latest_sync_outcome: str | None = None
    latest_sync_finished_at: datetime | None = None


def day_start(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


def search_sql(session: Session, query: CatalogQuery) -> CatalogResult:
    statement = select(Opportunity)
    if query.entity:
        statement = statement.where(Opportunity.entity.icontains(query.entity, autoescape=True))
    if query.location:
        statement = statement.where(or_(
            Opportunity.department.icontains(query.location, autoescape=True),
            Opportunity.city.icontains(query.location, autoescape=True),
        ))
    if query.closing_from:
        statement = statement.where(Opportunity.reception_at >= day_start(query.closing_from))
    if query.closing_to:
        statement = statement.where(
            Opportunity.reception_at < day_start(query.closing_to + timedelta(days=1))
        )
    if query.validity:
        status = func.lower(func.trim(Opportunity.status))
        phase = func.lower(func.trim(Opportunity.raw_payload["fase"].as_string()))
        offers = or_(status.in_(OFFERING), and_(status == "publicado", phase.in_(OFFER_PHASE)))
        now = datetime.now(UTC)
        state = case(
            (status.in_(CLOSED), "cerrado"),
            (and_(offers, Opportunity.reception_at > now), "abierto"),
            (and_(offers, Opportunity.reception_at <= now), "vencido"),
            else_="desconocida",
        )
        statement = statement.where(state == query.validity)
    if query.q:
        statement = statement.where(
            or_(
                Opportunity.title.icontains(query.q, autoescape=True),
                Opportunity.entity.icontains(query.q, autoescape=True),
                Opportunity.reference.icontains(query.q, autoescape=True),
            )
        )
    if query.status:
        statement = statement.where(Opportunity.status == query.status)
    if query.modality:
        statement = statement.where(Opportunity.modality == query.modality)
    if query.published_from:
        statement = statement.where(Opportunity.published_at >= day_start(query.published_from))
    if query.published_to:
        statement = statement.where(
            Opportunity.published_at < day_start(query.published_to + timedelta(days=1))
        )
    # Los nombres/direcciones nunca proceden de SQL libre del navegador.
    order = {
        "published_desc": Opportunity.published_at.desc(),
        "published_asc": Opportunity.published_at.asc(),
        "entity_asc": func.lower(Opportunity.entity).asc(),
        "title_asc": func.lower(Opportunity.title).asc(),
        "synced_desc": Opportunity.last_synced_at.desc(),
    }[query.sort]
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = list(
        session.scalars(
            statement.order_by(order.nullslast(), Opportunity.id.asc())
            .limit(query.limit)
            .offset(query.offset)
        )
    )
    synced = session.scalar(select(func.max(Opportunity.last_synced_at)))
    latest = session.scalar(
        select(SyncRun).where(SyncRun.dataset == PROCESSES_DATASET)
        .order_by(SyncRun.id.desc()).limit(1)
    )
    return CatalogResult(
        items,
        total,
        synced,
        latest.outcome if latest else None,
        latest.finished_at if latest else None,
    )


def search_memory(items: Sequence[Opportunity], query: CatalogQuery) -> CatalogResult:
    """Modo memoria ya existente; nunca introduce registros de demostración."""

    def aware(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    now = datetime.now(UTC)

    def matches(item: Opportunity) -> bool:
        if query.validity and (
            validity(item.status, item.phase, item.reception_at, now) != query.validity
        ):
            return False
        if query.entity and query.entity.casefold() not in (item.entity or "").casefold():
            return False
        if query.location and not any(
            query.location.casefold() in (value or "").casefold()
            for value in (item.city, item.department)
        ):
            return False
        if query.closing_from and (
            item.reception_at is None or aware(item.reception_at) < day_start(query.closing_from)
        ):
            return False
        if query.closing_to and (
            item.reception_at is None
            or aware(item.reception_at) >= day_start(query.closing_to + timedelta(days=1))
        ):
            return False
        if query.q and not any(
            query.q.casefold() in (v or "").casefold()
            for v in (item.title, item.entity, item.reference)
        ):
            return False
        if query.status and item.status != query.status:
            return False
        if query.modality and item.modality != query.modality:
            return False
        if query.published_from and (
            item.published_at is None or aware(item.published_at) < day_start(query.published_from)
        ):
            return False
        return not (
            query.published_to
            and (
                item.published_at is None
                or aware(item.published_at) >= day_start(query.published_to + timedelta(days=1))
            )
        )

    filtered = sorted((item for item in items if matches(item)), key=lambda item: item.id)
    field = {
        "published_desc": "published_at",
        "published_asc": "published_at",
        "entity_asc": "entity",
        "title_asc": "title",
        "synced_desc": "last_synced_at",
    }[query.sort]
    present = [item for item in filtered if getattr(item, field) is not None]
    missing = [item for item in filtered if getattr(item, field) is None]
    present.sort(
        key=lambda item: (
            getattr(item, field).casefold()
            if field in ("entity", "title")
            else aware(getattr(item, field))
        ),
        reverse=query.sort in ("published_desc", "synced_desc"),
    )
    ordered = present + missing
    return CatalogResult(
        ordered[query.offset : query.offset + query.limit],
        len(ordered),
        max((aware(item.last_synced_at) for item in items), default=None),
    )
