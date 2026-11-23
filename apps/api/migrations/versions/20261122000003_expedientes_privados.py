"""MVP-07: expedientes privados por oportunidad."""

import sqlalchemy as sa
from alembic import op

revision = "20261122000003"
down_revision = "20261122000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opportunity_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "opportunity_id", sa.BigInteger(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column("document_key", sa.String(256), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("title", sa.String(140), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("source_record_id", sa.String(160)),
        sa.Column("source_url", sa.Text()),
        sa.Column("source_verified_at", sa.DateTime(timezone=True)),
        sa.Column("source_evidence", sa.String(300)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("under_review", sa.Boolean(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id", "opportunity_id", "document_key", "version",
            name="uq_opportunity_document_version",
        ),
    )
    op.create_index(
        "ix_opportunity_documents_scope", "opportunity_documents",
        ["organization_id", "opportunity_id"],
    )
    op.create_table(
        "opportunity_document_contents",
        sa.Column(
            "document_id", sa.Uuid(),
            sa.ForeignKey("opportunity_documents.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
    )
    op.execute("ALTER TABLE opportunity_documents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE opportunity_document_contents ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON opportunity_documents, opportunity_document_contents FROM PUBLIC")
    op.execute("""
        DO $$
        DECLARE client_role text;
        BEGIN
            FOR client_role IN
                SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')
            LOOP
                EXECUTE format(
                    'REVOKE ALL ON opportunity_documents, opportunity_document_contents FROM %I',
                    client_role
                );
            END LOOP;
        END
        $$;
    """)


def downgrade() -> None:
    op.drop_table("opportunity_document_contents")
    op.drop_table("opportunity_documents")
