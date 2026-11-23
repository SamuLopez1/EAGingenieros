"""Selección privada de cada miembro."""

from uuid import UUID

from sqlalchemy import JSON, Integer, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base


class OpportunityShortlist(Base):
    __tablename__ = "opportunity_shortlists"

    organization_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    subject_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    opportunity_ids: Mapped[list[int]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
    )
