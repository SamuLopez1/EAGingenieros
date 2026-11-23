"""Historial append-only de revisiones humanas."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base


class DossierRevision(Base):
    __tablename__ = "comparison_dossier_revisions"

    organization_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        primary_key=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)


class ComparisonRevision(Base):
    __tablename__ = "comparison_revisions"
    __table_args__ = (Index("ix_comparison_revisions_expires_at", "expires_at"),)

    organization_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        primary_key=True,
    )
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    actor_role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    dossier_key: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    audit_details: Mapped[dict[str, object]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
    )
    corrections: Mapped[dict[str, object]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
