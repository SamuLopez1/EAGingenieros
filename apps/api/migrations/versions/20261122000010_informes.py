"""#12: auditoría privada e idempotente del envío de informes."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261122000010"
down_revision = "20261122000006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_deliveries",
        sa.Column("organization_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.BigInteger(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("recipient", sa.String(254), primary_key=True),
        sa.Column("id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("credential", sa.String(64), nullable=False),
        sa.Column("sender", sa.String(254), nullable=False),
        sa.Column("link", sa.String(2048), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("provider_id", sa.Uuid()),
        sa.Column("attempts", JSONB(), nullable=False),
    )
    op.execute("ALTER TABLE report_deliveries ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON report_deliveries FROM PUBLIC")
    op.execute("""
        DO $$
        DECLARE client_role text;
        BEGIN
            FOR client_role IN
                SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')
            LOOP
                EXECUTE format('REVOKE ALL ON report_deliveries FROM %I', client_role);
            END LOOP;
        END
        $$;
    """)


def downgrade() -> None:
    op.drop_table("report_deliveries")
