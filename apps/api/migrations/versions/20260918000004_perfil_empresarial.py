"""Perfil empresarial versionado con evidencia y vigencias.

Revision ID: 20260918000004
Revises: 20260918000003

Es la otra mitad de la comparación: el RAG recupera evidencia de los documentos,
este modelo estructura lo que la empresa afirma de sí misma.

Decisiones que se reflejan en el esquema:

  * Los valores son NULL cuando no constan, nunca cero. En una comparación de
    requisitos «no sé» y «vale cero» producen veredictos distintos.
  * Cada dato guarda su documento de evidencia y su estado de verificación. Un
    valor sin soporte puede mostrarse, pero no puede sostener un «cumple».
  * El perfil se versiona. Un análisis aprobado debe seguir apuntando a la
    versión que usó, y cambiar un patrimonio no debe alterar retroactivamente un
    informe ya emitido.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260918000004"
down_revision: str | None = "20260918000003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _evidence_columns() -> list[sa.Column]:
    """Columnas comunes de soporte documental, presentes en las cinco tablas."""

    return [
        sa.Column("evidence_document_id", sa.BigInteger(), nullable=True),
        sa.Column("evidence_locator", sa.String(length=300), nullable=True),
        sa.Column(
            "verification_status",
            sa.String(length=24),
            nullable=False,
            server_default="pendiente",
        ),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
    ]


def _evidence_constraints(table: str) -> list[sa.SchemaItem]:
    return [
        sa.ForeignKeyConstraint(
            ["evidence_document_id"], ["knowledge_documents.id"], ondelete="SET NULL"
        ),
    ] + [sa.PrimaryKeyConstraint("id") for _ in [0]]


def upgrade() -> None:
    op.create_table(
        "profile_versions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        # Obligatorio: un historial sin motivo no permite auditar por qué cambió
        # un cumplimiento de resultado entre dos análisis.
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_profile_versions_current", "profile_versions", ["is_current"])

    op.create_table(
        "profile_experience",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("profile_id", sa.BigInteger(), nullable=False),
        sa.Column("contract_reference", sa.String(length=200), nullable=True),
        sa.Column("entity", sa.Text(), nullable=True),
        sa.Column("object_description", sa.Text(), nullable=True),
        sa.Column("specialty", sa.String(length=200), nullable=True),
        sa.Column("role", sa.String(length=200), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        # Nullable a proposito: un contrato puede acreditar experiencia sin que
        # su valor conste, y forzar un cero convertiria «no consta» en «vale cero».
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        *_evidence_columns(),
        sa.ForeignKeyConstraint(["profile_id"], ["profile_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["evidence_document_id"], ["knowledge_documents.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_experience_profile", "profile_experience", ["profile_id"])
    op.create_index("ix_experience_specialty", "profile_experience", ["specialty"])

    op.create_table(
        "profile_personnel",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("profile_id", sa.BigInteger(), nullable=False),
        # Identificador interno, no documento de identidad: el perfil no necesita
        # identificar legalmente a la persona para comparar formacion.
        sa.Column("internal_id", sa.String(length=64), nullable=True),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("role", sa.String(length=200), nullable=True),
        sa.Column("education_level", sa.String(length=120), nullable=True),
        sa.Column("profession", sa.String(length=200), nullable=True),
        sa.Column("experience_years", sa.Integer(), nullable=True),
        sa.Column(
            "certifications",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        *_evidence_columns(),
        sa.ForeignKeyConstraint(["profile_id"], ["profile_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["evidence_document_id"], ["knowledge_documents.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_personnel_profile", "profile_personnel", ["profile_id"])

    op.create_table(
        "profile_capabilities",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("profile_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        # Cantidad con unidad explícita: un «3» sin unidad no es comparable.
        sa.Column("quantity", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("unit", sa.String(length=40), nullable=True),
        *_evidence_columns(),
        sa.ForeignKeyConstraint(["profile_id"], ["profile_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["evidence_document_id"], ["knowledge_documents.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_capabilities_profile", "profile_capabilities", ["profile_id"])

    op.create_table(
        "profile_financials",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("profile_id", sa.BigInteger(), nullable=False),
        sa.Column("indicator", sa.String(length=120), nullable=False),
        sa.Column("period", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("unit", sa.String(length=40), nullable=True),
        # Sin formula, dos personas obtienen valores distintos del mismo estado
        # financiero y ninguna sabe por que.
        sa.Column("formula", sa.Text(), nullable=True),
        *_evidence_columns(),
        sa.ForeignKeyConstraint(["profile_id"], ["profile_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["evidence_document_id"], ["knowledge_documents.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        # Dos valores distintos del mismo indicador y periodo harian ambigua la
        # comparacion.
        sa.UniqueConstraint("profile_id", "indicator", "period", name="uq_financial_period"),
    )
    op.create_index("ix_financials_profile", "profile_financials", ["profile_id"])

    op.create_table(
        "profile_legal",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("profile_id", sa.BigInteger(), nullable=False),
        sa.Column("document_type", sa.String(length=120), nullable=False),
        sa.Column("identifier", sa.String(length=200), nullable=True),
        sa.Column("issuer", sa.String(length=200), nullable=True),
        sa.Column("issued_on", sa.Date(), nullable=True),
        # `valid_until` llega en _evidence_columns: declararlo aquí lo duplicaría.
        *_evidence_columns(),
        sa.ForeignKeyConstraint(["profile_id"], ["profile_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["evidence_document_id"], ["knowledge_documents.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_legal_profile", "profile_legal", ["profile_id"])


def downgrade() -> None:
    for table, indexes in [
        ("profile_legal", ["ix_legal_profile"]),
        ("profile_financials", ["ix_financials_profile"]),
        ("profile_capabilities", ["ix_capabilities_profile"]),
        ("profile_personnel", ["ix_personnel_profile"]),
        ("profile_experience", ["ix_experience_specialty", "ix_experience_profile"]),
    ]:
        for index in indexes:
            op.drop_index(index, table_name=table)
        op.drop_table(table)
    op.drop_index("ix_profile_versions_current", table_name="profile_versions")
    op.drop_table("profile_versions")
