"""Registra los límites de una ventana incremental para retomarla."""

import sqlalchemy as sa
from alembic import op

revision = "20261122000001"
down_revision = "20260917000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sync_runs", sa.Column("window_start", sa.DateTime(timezone=True)))
    op.add_column("sync_runs", sa.Column("window_end", sa.DateTime(timezone=True)))
    op.add_column(
        "sync_runs", sa.Column("window_checkpoint", sa.Boolean(), nullable=False,
                               server_default=sa.false())
    )


def downgrade() -> None:
    op.drop_column("sync_runs", "window_checkpoint")
    op.drop_column("sync_runs", "window_end")
    op.drop_column("sync_runs", "window_start")
