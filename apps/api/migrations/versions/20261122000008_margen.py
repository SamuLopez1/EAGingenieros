"""#24: escenarios financieros privados y versionados."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261122000008"
down_revision = "20261122000007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "margin_versions",
        sa.Column("organization_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.BigInteger(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("scenario_id", sa.Uuid(), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(400)),
        sa.Column("inputs", JSONB(), nullable=False),
        sa.Column("basis", JSONB(), nullable=False),
        sa.Column("calculation", JSONB(), nullable=False),
        sa.Column("rules_version", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute("ALTER TABLE margin_versions ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON margin_versions FROM PUBLIC")
    op.execute("""
        DO $$
        DECLARE client_role text;
        BEGIN
            FOR client_role IN
                SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')
            LOOP
                EXECUTE format('REVOKE ALL ON margin_versions FROM %I', client_role);
            END LOOP;
        END
        $$;
    """)


def downgrade() -> None:
    op.drop_table("margin_versions")
