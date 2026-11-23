"""MVP-06: campos consultables del catálogo y filtros compartidos."""

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects.postgresql import JSONB

from app.opportunity_fields import source_fields

revision = "20261122000002"
down_revision = "20261122000001"
branch_labels = None
depends_on = None


def backfill() -> None:
    connection = op.get_bind()
    opportunities = sa.table(
        "opportunities",
        sa.column("id", sa.BigInteger()),
        sa.column("raw_payload", JSONB()),
        sa.column("department", sa.Text()),
        sa.column("city", sa.Text()),
        sa.column("reception_at", sa.DateTime(timezone=True)),
    )
    last_id = 0
    patch = opportunities.update().where(opportunities.c.id == sa.bindparam("source_row_id"))
    while True:
        batch = connection.execute(
            sa.select(opportunities.c.id, opportunities.c.raw_payload)
            .where(opportunities.c.id > last_id)
            .order_by(opportunities.c.id)
            .limit(1000)
        ).all()
        if not batch:
            return
        connection.execute(
            patch, [{"source_row_id": row.id, **source_fields(row.raw_payload)} for row in batch]
        )
        last_id = batch[-1].id


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("Aplicar esta revisión en la base para completar los datos existentes.")
    op.add_column("opportunities", sa.Column("department", sa.Text()))
    op.add_column("opportunities", sa.Column("city", sa.Text()))
    op.add_column("opportunities", sa.Column("reception_at", sa.DateTime(timezone=True)))
    backfill()
    op.create_index("ix_opportunities_reception_at", "opportunities", ["reception_at"])
    op.create_table(
        "saved_opportunity_filters",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("criteria", JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "name", name="uq_saved_filter_org_name"),
    )
    op.create_index(
        "ix_saved_opportunity_filters_organization_id",
        "saved_opportunity_filters",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_table("saved_opportunity_filters")
    op.drop_index("ix_opportunities_reception_at", table_name="opportunities")
    op.drop_column("opportunities", "reception_at")
    op.drop_column("opportunities", "city")
    op.drop_column("opportunities", "department")
