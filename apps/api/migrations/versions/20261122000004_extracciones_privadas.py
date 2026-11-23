"""MVP-08: cola y resultados privados por versión de documento."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261122000004"
down_revision = "20261122000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_extractions",
        sa.Column(
            "document_id", sa.Uuid(),
            sa.ForeignKey("opportunity_documents.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "opportunity_id", sa.BigInteger(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("lease_token", sa.Uuid()),
        sa.Column("result", JSONB()),
    )
    op.create_index(
        "ix_document_extractions_queue", "document_extractions", ["status", "queued_at"],
    )
    op.execute("ALTER TABLE document_extractions ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON document_extractions FROM PUBLIC")
    op.execute("""
        DO $$
        DECLARE client_role text;
        BEGIN
            FOR client_role IN
                SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')
            LOOP
                EXECUTE format('REVOKE ALL ON document_extractions FROM %I', client_role);
            END LOOP;
        END
        $$;
    """)


def downgrade() -> None:
    op.drop_table("document_extractions")
