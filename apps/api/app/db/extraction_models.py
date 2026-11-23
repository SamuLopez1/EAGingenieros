"""Una tarea privada de extracción por versión física del documento."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base


class DocumentExtraction(Base):
    __tablename__ = "document_extractions"
    __table_args__ = (Index("ix_document_extractions_queue", "status", "queued_at"),)

    document_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("opportunity_documents.id", ondelete="CASCADE"), primary_key=True,
    )
    opportunity_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False,
    )
    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    result: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True).with_variant(JSON(none_as_null=True), "sqlite")
    )
