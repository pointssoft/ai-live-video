import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKeyConstraint, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PortraitStatus(enum.StrEnum):
    READY = "READY"
    DELETED = "DELETED"


class Portrait(Base):
    __tablename__ = "portraits"
    __table_args__ = (
        UniqueConstraint("original_asset_id", name="uq_portraits_original_asset"),
        UniqueConstraint("thumbnail_asset_id", name="uq_portraits_thumbnail_asset"),
        UniqueConstraint("id", "user_id", name="uq_portraits_id_user"),
        ForeignKeyConstraint(
            ["original_asset_id", "user_id"],
            ["media_assets.id", "media_assets.user_id"],
            ondelete="RESTRICT",
            name="fk_portraits_original_asset_owner",
        ),
        ForeignKeyConstraint(
            ["thumbnail_asset_id", "user_id"],
            ["media_assets.id", "media_assets.user_id"],
            ondelete="RESTRICT",
            name="fk_portraits_thumbnail_asset_owner",
        ),
        Index("ix_portraits_user_created", "user_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    original_asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    thumbnail_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(32), default=PortraitStatus.READY.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
