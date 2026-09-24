"""Persistencia del análisis de requisitos, revisión y aprobación por snapshot.

Revision ID: 20260923000006
Revises: 20260923000005

Sin estas tablas el análisis se devolvía en la respuesta HTTP y no quedaba
registrado, así que la épica E7 no se podía cumplir: corregir un requisito
(HU-32), aprobar una versión concreta (HU-33) o bloquear el informe cuando las
entradas cambian (HU-34) exigen que el análisis sea un registro consultable.

Decisiones que se reflejan en el esquema:

  * La salida automática nunca se sobrescribe. La corrección humana es una fila
    nueva en `analysis_reviews` con autor, fecha y motivo. Si se modificara la
    original, el piloto no podría medir en qué discrepa el sistema de la persona
    (HU-32, HU-42).

  * `analysis_matches` guarda entradas, regla, resultado y motivo, que es lo que
    HU-29 exige para que un cálculo sea auditable y reproducible.

  * La aprobación guarda una **firma** de lo aprobado —documentos con versión,
    versión del perfil y decisiones—. Aprobar es congelar (decisión A4), no
    marcar: la aprobación sigue vigente mientras la firma coincida, y un cambio
    posterior la deja sin efecto sin necesidad de perseguir qué cambió.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260923000006"
down_revision: str | None = "20260923000005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Ejecuciones -------------------------------------------------------
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("opportunity_id", sa.BigInteger(), nullable=False),
        sa.Column("started_by", sa.BigInteger(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="en_curso"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("documents_read", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunks_available", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requirements_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requirements_rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_id", sa.String(length=120), nullable=True),
        sa.Column("prompt_version", sa.String(length=40), nullable=True),
        sa.Column("schema_version", sa.String(length=40), nullable=True),
        sa.Column("graph_thread_id", sa.String(length=120), nullable=False),
        sa.Column(
            "steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"
        ),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["started_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("graph_thread_id", name="uq_analysis_run_thread"),
    )
    op.create_index("ix_analysis_run_opportunity", "analysis_runs", ["opportunity_id"])
    op.create_index("ix_analysis_run_status", "analysis_runs", ["status"])

    # --- Requisitos --------------------------------------------------------
    op.create_table(
        "analysis_requirements",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=True),
        sa.Column("source_document_id", sa.BigInteger(), nullable=True),
        sa.Column("source_locator", sa.String(length=300), nullable=True),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column(
            "citation_verified", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("validation_note", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_document_id"], ["knowledge_documents.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_requirement_run", "analysis_requirements", ["run_id"])

    # --- Propuestas de estado ---------------------------------------------
    op.create_table(
        "analysis_matches",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("requirement_id", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column(
            "decided_by", sa.String(length=16), nullable=False, server_default="recuperacion"
        ),
        sa.Column("rule", sa.String(length=80), nullable=True),
        sa.Column(
            "inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column(
            "evidence_chunk_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"], ["analysis_requirements.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_match_requirement", "analysis_matches", ["requirement_id"])

    # --- Correcciones humanas ---------------------------------------------
    op.create_table(
        "analysis_reviews",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("match_id", sa.BigInteger(), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_state", sa.String(length=24), nullable=False),
        sa.Column("new_state", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "evidence_chunk_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["match_id"], ["analysis_matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_review_match", "analysis_reviews", ["match_id"])

    # --- Aprobación por snapshot (A4) -------------------------------------
    op.create_table(
        "analysis_approvals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("approved_by", sa.BigInteger(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_signature", sa.String(length=64), nullable=False),
        sa.Column(
            "snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column("profile_version_id", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["profile_version_id"], ["profile_versions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        # Una aprobación por ejecución: aprobar dos veces lo mismo no significa
        # nada, y permitirlo abriría la puerta a que gane la última escritura.
        sa.UniqueConstraint("run_id"),
    )


def downgrade() -> None:
    op.drop_table("analysis_approvals")
    op.drop_index("ix_analysis_review_match", table_name="analysis_reviews")
    op.drop_table("analysis_reviews")
    op.drop_index("ix_analysis_match_requirement", table_name="analysis_matches")
    op.drop_table("analysis_matches")
    op.drop_index("ix_analysis_requirement_run", table_name="analysis_requirements")
    op.drop_table("analysis_requirements")
    op.drop_index("ix_analysis_run_status", table_name="analysis_runs")
    op.drop_index("ix_analysis_run_opportunity", table_name="analysis_runs")
    op.drop_table("analysis_runs")
