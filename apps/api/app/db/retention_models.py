"""Metadatos mínimos para reaplicar purgas después de restaurar."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base


class RetentionTombstone(Base):
    __tablename__ = "retention_tombstones"
    __table_args__ = (
        Index("ix_retention_comparison", "kind", "organization_id", "opportunity_id", "revision"),
    )

    key: Mapped[str] = mapped_column(String(104), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    opportunity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    object_id: Mapped[UUID | None] = mapped_column(Uuid)
    revision: Mapped[int | None] = mapped_column(Integer)
    purged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
