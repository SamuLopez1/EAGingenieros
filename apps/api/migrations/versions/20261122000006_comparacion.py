"""MVP-11: unión de dependencias y auditoría privada de comparación."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261122000006"
down_revision = ("20261122000004", "20261122000005")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "comparison_dossier_revisions",
        sa.Column("organization_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.BigInteger(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.create_table(
        "comparison_revisions",
        sa.Column("organization_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.BigInteger(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("actor_role", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("dossier_key", sa.String(64), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("audit_details", JSONB(), nullable=False),
        sa.Column("corrections", JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    for table in ("comparison_dossier_revisions", "comparison_revisions"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        op.execute(f"""
            DO $$
            DECLARE client_role text;
            BEGIN
                FOR client_role IN
                    SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')
                LOOP
                    EXECUTE format('REVOKE ALL ON {table} FROM %I', client_role);
                END LOOP;
            END
            $$;
        """)


def downgrade() -> None:
    op.drop_table("comparison_revisions")
    op.drop_table("comparison_dossier_revisions")
