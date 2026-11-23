"""MVP-09: perfil maestro por organización y versión."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261122000005"
down_revision = "20261122000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_profile_versions",
        sa.Column("organization_id", sa.Uuid(), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entries", JSONB(), nullable=False),
    )
    op.create_table(
        "company_profile_evidence",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.UniqueConstraint("organization_id", "sha256", name="uq_profile_evidence_sha"),
    )
    for table in ("company_profile_versions", "company_profile_evidence"):
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
    op.drop_table("company_profile_evidence")
    op.drop_table("company_profile_versions")
