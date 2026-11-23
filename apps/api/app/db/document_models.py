"""Metadatos y contenido privado del expediente."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base


class OpportunityDocument(Base):
    __tablename__ = "opportunity_documents"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "opportunity_id", "document_key", "version",
            name="uq_opportunity_document_version",
        ),
        Index("ix_opportunity_documents_scope", "organization_id", "opportunity_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    opportunity_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    uploaded_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    document_key: Mapped[str] = mapped_column(String(256), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(140), nullable=False)
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(String(160))
    source_url: Mapped[str | None] = mapped_column(Text)
    source_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_evidence: Mapped[str | None] = mapped_column(String(300))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    under_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OpportunityDocumentContent(Base):
    __tablename__ = "opportunity_document_contents"

    document_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("opportunity_documents.id", ondelete="CASCADE"), primary_key=True
    )
    payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
