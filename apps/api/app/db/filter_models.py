"""Configuración compartida de búsqueda, aislada por organización."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, BigInteger, DateTime, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base, utcnow


class SavedOpportunityFilter(Base):
    __tablename__ = "saved_opportunity_filters"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_saved_filter_org_name"),)

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    criteria: Mapped[dict[str, object]] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
