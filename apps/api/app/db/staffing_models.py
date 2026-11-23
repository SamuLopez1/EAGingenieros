"""Correcciones de planificación ligadas a las entradas de comparación."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base


class StaffingCorrection(Base):
    __tablename__ = "staffing_corrections"

    organization_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        primary_key=True,
    )
    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    comparison_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    row_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    previous: Mapped[dict[str, object]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
    )
    corrected: Mapped[dict[str, object]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
    )
