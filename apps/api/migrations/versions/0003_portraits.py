"""portrait library

Revision ID: 0003_portraits
Revises: 0002_media_validation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_portraits"
down_revision: str | None = "0002_media_validation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("media_assets", sa.Column("purged_at", sa.DateTime(timezone=True)))
    op.create_unique_constraint("uq_media_id_user", "media_assets", ["id", "user_id"])
    op.create_table(
        "portraits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thumbnail_asset_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('READY', 'DELETED')", name="ck_portraits_status"),
        sa.UniqueConstraint("original_asset_id", name="uq_portraits_original_asset"),
        sa.UniqueConstraint("thumbnail_asset_id", name="uq_portraits_thumbnail_asset"),
        sa.ForeignKeyConstraint(
            ["original_asset_id", "user_id"],
            ["media_assets.id", "media_assets.user_id"],
            ondelete="RESTRICT",
            name="fk_portraits_original_asset_owner",
        ),
        sa.ForeignKeyConstraint(
            ["thumbnail_asset_id", "user_id"],
            ["media_assets.id", "media_assets.user_id"],
            ondelete="RESTRICT",
            name="fk_portraits_thumbnail_asset_owner",
        ),
    )
    op.create_index("ix_portraits_user_created", "portraits", ["user_id", "created_at", "id"])


def downgrade() -> None:
    op.drop_table("portraits")
    op.drop_constraint("uq_media_id_user", "media_assets", type_="unique")
    op.drop_column("media_assets", "purged_at")
