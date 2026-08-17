import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GenerationStatus(enum.StrEnum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELED = "CANCELED"


class Generation(Base):
    __tablename__ = "generations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('CREATED', 'QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', "
            "'TIMED_OUT', 'CANCEL_REQUESTED', 'CANCELED')",
            name="ck_generations_status",
        ),
        CheckConstraint(
            "(idempotency_key IS NULL AND request_fingerprint IS NULL) OR "
            "(idempotency_key IS NOT NULL AND request_fingerprint IS NOT NULL)",
            name="ck_generations_idempotency_pair",
        ),
        CheckConstraint(
            "request_fingerprint IS NULL OR "
            "request_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_generations_request_fingerprint",
        ),
        Index(
            "uq_generations_user_idempotency_key",
            "user_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        ForeignKeyConstraint(
            ["portrait_id", "user_id"],
            ["portraits.id", "portraits.user_id"],
            ondelete="RESTRICT",
            name="fk_generations_portrait_owner",
        ),
        ForeignKeyConstraint(
            ["motion_asset_id", "user_id"],
            ["media_assets.id", "media_assets.user_id"],
            ondelete="RESTRICT",
            name="fk_generations_motion_asset_owner",
        ),
        Index("ix_generations_user_created", "user_id", "created_at", "id"),
        Index("ix_generations_status_updated", "status", "updated_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    portrait_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    motion_asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=GenerationStatus.CREATED.value)
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    request_fingerprint: Mapped[str | None] = mapped_column(String(64))
    output_object_key: Mapped[str | None] = mapped_column(String(512))
    output_content_type: Mapped[str | None] = mapped_column(String(100))
    output_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    output_sha256: Mapped[str | None] = mapped_column(String(64))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    failure_message: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timed_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
