"""#23: historial privado de correcciones de personal."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261122000007"
down_revision = "20261122000006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staffing_corrections",
        sa.Column("organization_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.BigInteger(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("fingerprint", sa.String(64), primary_key=True),
        sa.Column("sequence", sa.Integer(), primary_key=True),
        sa.Column("comparison_revision", sa.Integer(), nullable=False),
        sa.Column("row_id", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous", JSONB(), nullable=False),
        sa.Column("corrected", JSONB(), nullable=False),
    )
    op.execute("ALTER TABLE staffing_corrections ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON staffing_corrections FROM PUBLIC")
    op.execute("""
        DO $$
        DECLARE client_role text;
        BEGIN
            FOR client_role IN
                SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')
            LOOP
                EXECUTE format('REVOKE ALL ON staffing_corrections FROM %I', client_role);
            END LOOP;
        END
        $$;
    """)


def downgrade() -> None:
    op.drop_table("staffing_corrections")
