"""Registro de consumo de IA y caché de llamadas.

Revision ID: 20260923000007
Revises: 20260923000006

HU-27 exige limitar tokens, llamadas repetidas y coste. Un tope mensual solo se
puede aplicar si el gasto acumulado es consultable y **sobrevive a los
reinicios**: un contador en memoria se pondría a cero con cada despliegue, justo
cuando el control hace más falta.

Dos tablas con propósitos distintos:

  * `ai_usage` es el libro de consumo. Una fila por llamada, con su modelo, su
    versión de prompt y su coste estimado. Responde «cuánto se gastó» y «qué
    modelo produjo este resultado». Se registran también las llamadas fallidas y
    las omitidas por presupuesto: las primeras pueden haber consumido entrada
    —el proveedor la cobra aunque la salida se trunque— y las segundas son un
    resultado legítimo que no debe confundirse con una avería.

  * `ai_cache` evita pagar dos veces por el mismo trabajo. La clave incluye
    modelo y versión de prompt además del contenido, así que cambiar de modelo
    invalida la caché por construcción en lugar de depender de que alguien se
    acuerde de purgarla.

`cost_usd` admite NULL y no lleva valor por defecto: un modelo sin tarifa
conocida no es gratis, es desconocido, y poner cero afirmaría lo contrario.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260923000007"
down_revision: str | None = "20260923000006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("analysis_run_id", sa.BigInteger(), nullable=True),
        sa.Column("node", sa.String(length=64), nullable=True),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("prompt_version", sa.String(length=40), nullable=True),
        sa.Column("schema_version", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completada"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "usage_reported", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("cache_key", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_kind", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_usage_created_at", "ai_usage", ["created_at"])
    op.create_index("ix_ai_usage_run", "ai_usage", ["analysis_run_id"])
    op.create_index("ix_ai_usage_status", "ai_usage", ["status"])

    op.create_table(
        "ai_cache",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("schema_version", sa.String(length=40), nullable=True),
        sa.Column(
            "payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "cache_key", "model", "prompt_version", name="uq_ai_cache_entry"
        ),
    )
    op.create_index("ix_ai_cache_created_at", "ai_cache", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_cache_created_at", table_name="ai_cache")
    op.drop_table("ai_cache")
    op.drop_index("ix_ai_usage_status", table_name="ai_usage")
    op.drop_index("ix_ai_usage_run", table_name="ai_usage")
    op.drop_index("ix_ai_usage_created_at", table_name="ai_usage")
    op.drop_table("ai_usage")
