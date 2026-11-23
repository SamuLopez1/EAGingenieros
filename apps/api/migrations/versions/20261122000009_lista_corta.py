"""#34: lista corta privada por persona y organización."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261122000009"
down_revision = "20261122000008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opportunity_shortlists",
        sa.Column("organization_id", sa.Uuid(), primary_key=True),
        sa.Column("subject_id", sa.Uuid(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("opportunity_ids", JSONB(), nullable=False),
    )
    op.execute("ALTER TABLE opportunity_shortlists ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON opportunity_shortlists FROM PUBLIC")
    op.execute("""
        DO $$
        DECLARE client_role text;
        BEGIN
            FOR client_role IN
                SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')
            LOOP
                EXECUTE format('REVOKE ALL ON opportunity_shortlists FROM %I', client_role);
            END LOOP;
        END
        $$;
    """)


def downgrade() -> None:
    op.drop_table("opportunity_shortlists")
