import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MediaKind(enum.StrEnum):
    PORTRAIT_ORIGINAL = "PORTRAIT_ORIGINAL"
    MOTION_INPUT = "MOTION_INPUT"


class MediaState(enum.StrEnum):
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    VALIDATING = "VALIDATING"
    READY = "READY"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    UPLOAD_EXPIRED = "UPLOAD_EXPIRED"
    UPLOAD_FAILED = "UPLOAD_FAILED"
    DELETED = "DELETED"


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        Index("ix_media_user_state_created", "user_id", "state", "created_at"),
        Index("ix_media_state_expires", "state", "upload_expires_at"),
        Index("ix_media_validation_claim", "state", "validation_lease_expires_at"),
        UniqueConstraint("id", "user_id", name="uq_media_id_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(32))
    object_key: Mapped[str] = mapped_column(String(512), unique=True)
    content_type: Mapped[str] = mapped_column(String(100))
    detected_content_type: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    provider_etag: Mapped[str | None] = mapped_column(String(255))
    state: Mapped[str] = mapped_column(String(32), default=MediaState.UPLOADING.value)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    fps: Mapped[float | None] = mapped_column(Float)
    frame_count: Mapped[int | None] = mapped_column(Integer)
    video_codec: Mapped[str | None] = mapped_column(String(32))
    validation_attempts: Mapped[int] = mapped_column(Integer, default=0)
    validation_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validation_lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validation_lease_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validation_error_code: Mapped[str | None] = mapped_column(String(64))
    validation_error_detail: Mapped[str | None] = mapped_column(String(255))
    upload_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
