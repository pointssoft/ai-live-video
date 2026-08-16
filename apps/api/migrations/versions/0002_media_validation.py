"""media validation metadata

Revision ID: 0002_media_validation
Revises: 0001_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_media_validation"
down_revision: str | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("media_assets", sa.Column("detected_content_type", sa.String(100)))
    op.add_column("media_assets", sa.Column("width", sa.Integer()))
    op.add_column("media_assets", sa.Column("height", sa.Integer()))
    op.add_column("media_assets", sa.Column("duration_ms", sa.Integer()))
    op.add_column("media_assets", sa.Column("fps", sa.Float()))
    op.add_column("media_assets", sa.Column("frame_count", sa.Integer()))
    op.add_column("media_assets", sa.Column("video_codec", sa.String(32)))
    op.add_column(
        "media_assets",
        sa.Column("validation_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("media_assets", sa.Column("validation_started_at", sa.DateTime(timezone=True)))
    op.add_column(
        "media_assets", sa.Column("validation_lease_expires_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "media_assets", sa.Column("validation_lease_token", postgresql.UUID(as_uuid=True))
    )
    op.add_column("media_assets", sa.Column("validated_at", sa.DateTime(timezone=True)))
    op.add_column("media_assets", sa.Column("ready_at", sa.DateTime(timezone=True)))
    op.add_column("media_assets", sa.Column("validation_error_code", sa.String(64)))
    op.add_column("media_assets", sa.Column("validation_error_detail", sa.String(255)))
    op.add_column(
        "media_assets",
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_media_validation_claim",
        "media_assets",
        ["state", "validation_lease_expires_at"],
    )
    op.create_check_constraint(
        "ck_media_validation_attempts_nonnegative", "media_assets", "validation_attempts >= 0"
    )


def downgrade() -> None:
    op.drop_constraint("ck_media_validation_attempts_nonnegative", "media_assets", type_="check")
    op.drop_index("ix_media_validation_claim", table_name="media_assets")
    for column in (
        "updated_at",
        "validation_error_detail",
        "validation_error_code",
        "ready_at",
        "validated_at",
        "validation_lease_token",
        "validation_lease_expires_at",
        "validation_started_at",
        "validation_attempts",
        "video_codec",
        "frame_count",
        "fps",
        "duration_ms",
        "height",
        "width",
        "detected_content_type",
    ):
        op.drop_column("media_assets", column)
