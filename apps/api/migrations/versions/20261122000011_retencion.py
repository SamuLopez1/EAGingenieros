"""#13: retención de expedientes y registro mínimo de purgas."""

import sqlalchemy as sa
from alembic import op

revision = "20261122000011"
down_revision = "20261122000010"
branch_labels = None
depends_on = None

DEADLINES = (
    ("opportunity_documents", "retention_until"),
    ("comparison_revisions", "expires_at"),
    ("report_deliveries", "expires_at"),
)


def upgrade() -> None:
    op.create_table(
        "retention_tombstones",
        sa.Column("key", sa.String(104), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.BigInteger(), nullable=False),
        sa.Column("object_id", sa.Uuid()),
        sa.Column("revision", sa.Integer()),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_retention_comparison",
        "retention_tombstones",
        ["kind", "organization_id", "opportunity_id", "revision"],
    )
    for table, column in DEADLINES:
        op.create_index(f"ix_{table}_{column}", table, [column])
    op.execute("ALTER TABLE retention_tombstones ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON retention_tombstones FROM PUBLIC")
    op.execute("""
        DO $$
        DECLARE client_role text;
        BEGIN
            FOR client_role IN
                SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')
            LOOP
                EXECUTE format('REVOKE ALL ON retention_tombstones FROM %I', client_role);
            END LOOP;
        END
        $$;
    """)


def downgrade() -> None:
    for table, column in reversed(DEADLINES):
        op.drop_index(f"ix_{table}_{column}", table_name=table)
    op.drop_table("retention_tombstones")
