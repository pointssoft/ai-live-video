"""phase 2c generation deletion and quotas

Revision ID: 0009_phase2c_deletion_quotas
Revises: 0008_phase2b_retries_webhooks
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_phase2c_deletion_quotas"
down_revision: str | None = "0008_phase2b_retries_webhooks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("generations", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.add_column("generations", sa.Column("purge_after_at", sa.DateTime(timezone=True)))
    op.add_column("generations", sa.Column("output_purged_at", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_generations_output_purge",
        "generations",
        ["deleted_at", "purge_after_at", "output_purged_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_generations_output_purge", table_name="generations")
    op.drop_column("generations", "output_purged_at")
    op.drop_column("generations", "purge_after_at")
    op.drop_column("generations", "deleted_at")
