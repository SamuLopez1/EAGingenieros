"""Oportunidades, ejecuciones de sincronización y cursor.

Revision ID: 20260917000001
Revises:
Create Date: 2026-09-17

Primera migración de negocio del MVP. Crea:

- ``opportunities``: catálogo de oportunidades oficiales. La restricción única
  sobre ``(source_dataset, source_id)`` es la base de la sincronización
  idempotente: la misma fila oficial vista dos veces actualiza el mismo
  registro en lugar de crear un duplicado.
- ``sync_runs``: historial de ejecuciones. Permite que un fallo parcial quede
  visible y reanudable en lugar de pasar por éxito.
- ``sync_cursors``: posición por conjunto de datos, para reanudar sin
  reiniciar el recorrido.

No crea tablas de documentos, análisis ni informes: corresponden a issues
posteriores y no deben adelantarse.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260917000001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "opportunities",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_dataset", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("reference", sa.String(length=256), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("entity", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("modality", sa.String(length=128), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("official_url", sa.Text(), nullable=True),
        # Carga original de la fuente: permite auditar y renormalizar sin red.
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_dataset", "source_id", name="uq_opportunity_source"),
    )
    op.create_index("ix_opportunity_published_at", "opportunities", ["published_at"])
    op.create_index("ix_opportunity_entity", "opportunities", ["entity"])
    op.create_index("ix_opportunity_status", "opportunities", ["status"])

    op.create_table(
        "sync_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("dataset", sa.String(length=32), nullable=False),
        sa.Column("records_seen", sa.Integer(), nullable=False),
        sa.Column("records_created", sa.Integer(), nullable=False),
        sa.Column("records_updated", sa.Integer(), nullable=False),
        sa.Column("records_skipped", sa.Integer(), nullable=False),
        sa.Column("requests_made", sa.Integer(), nullable=False),
        sa.Column("last_offset", sa.Integer(), nullable=False),
        sa.Column("error_kind", sa.String(length=64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sync_runs_started_at", "sync_runs", ["started_at"])

    op.create_table(
        "sync_cursors",
        sa.Column("dataset", sa.String(length=32), nullable=False),
        sa.Column("last_offset", sa.Integer(), nullable=False),
        sa.Column("last_run_id", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["last_run_id"], ["sync_runs.id"]),
        sa.PrimaryKeyConstraint("dataset"),
    )


def downgrade() -> None:
    op.drop_table("sync_cursors")
    op.drop_index("ix_sync_runs_started_at", table_name="sync_runs")
    op.drop_table("sync_runs")
    op.drop_index("ix_opportunity_status", table_name="opportunities")
    op.drop_index("ix_opportunity_entity", table_name="opportunities")
    op.drop_index("ix_opportunity_published_at", table_name="opportunities")
    op.drop_table("opportunities")
