"""generation request catalog

Revision ID: 0004_generations
Revises: 0003_portraits
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_generations"
down_revision: str | None = "0003_portraits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_portraits_id_user", "portraits", ["id", "user_id"])
    op.create_table(
        "generations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("portrait_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("motion_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("canceled_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('CREATED', 'CANCELED')", name="ck_generations_status"
        ),
        sa.ForeignKeyConstraint(
            ["portrait_id", "user_id"],
            ["portraits.id", "portraits.user_id"],
            ondelete="RESTRICT",
            name="fk_generations_portrait_owner",
        ),
        sa.ForeignKeyConstraint(
            ["motion_asset_id", "user_id"],
            ["media_assets.id", "media_assets.user_id"],
            ondelete="RESTRICT",
            name="fk_generations_motion_asset_owner",
        ),
    )
    op.create_index(
        "ix_generations_user_created", "generations", ["user_id", "created_at", "id"]
    )


def downgrade() -> None:
    op.drop_table("generations")
    op.drop_constraint("uq_portraits_id_user", "portraits", type_="unique")
