import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RunpodWebhookEvent(Base):
    __tablename__ = "runpod_webhook_events"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_runpod_webhook_dedupe_key"),
        Index("ix_runpod_webhook_job_received", "runpod_job_id", "received_at"),
        Index("ix_runpod_webhook_unprocessed", "processed_at", "received_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="runpod")
    provider_event_id: Mapped[str | None] = mapped_column(String(255))
    runpod_job_id: Mapped[str] = mapped_column(String(255), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_status: Mapped[str] = mapped_column(String(32), nullable=False)
    authentication_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_lease_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    processing_lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_error: Mapped[str | None] = mapped_column(String(255))
