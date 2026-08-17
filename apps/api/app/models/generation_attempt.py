import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GenerationAttemptStatus(enum.StrEnum):
    PENDING = "PENDING"
    SUBMITTING = "SUBMITTING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELED = "CANCELED"
    SUBMISSION_UNKNOWN = "SUBMISSION_UNKNOWN"


class GenerationAttempt(Base):
    __tablename__ = "generation_attempts"
    __table_args__ = (
        CheckConstraint("attempt_number >= 1", name="ck_generation_attempt_number"),
        CheckConstraint(
            "submission_attempts >= 0 AND poll_attempts >= 0",
            name="ck_generation_attempt_counters",
        ),
        CheckConstraint(
            "status <> 'SUBMISSION_UNKNOWN' OR "
            "(runpod_job_id IS NULL AND finished_at IS NOT NULL)",
            name="ck_generation_attempt_submission_unknown",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'SUBMITTING', 'QUEUED', 'RUNNING', 'SUCCEEDED', "
            "'FAILED', 'TIMED_OUT', 'CANCEL_REQUESTED', 'CANCELED', 'SUBMISSION_UNKNOWN')",
            name="ck_generation_attempts_status",
        ),
        CheckConstraint(
            "(retry_idempotency_key IS NULL AND retry_request_fingerprint IS NULL) OR "
            "(retry_idempotency_key IS NOT NULL AND retry_request_fingerprint IS NOT NULL)",
            name="ck_generation_attempt_retry_idempotency_pair",
        ),
        CheckConstraint(
            "retry_request_fingerprint IS NULL OR "
            "retry_request_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_generation_attempt_retry_fingerprint",
        ),
        UniqueConstraint(
            "generation_id", "attempt_number", name="uq_generation_attempt_number"
        ),
        UniqueConstraint("runpod_job_id", name="uq_generation_attempt_runpod_job"),
        Index(
            "ix_generation_attempt_claim",
            "status",
            "next_poll_at",
            "lease_expires_at",
        ),
        Index(
            "ix_generation_attempt_generation", "generation_id", "attempt_number"
        ),
        Index(
            "uq_generation_attempt_retry_key",
            "generation_id",
            "retry_idempotency_key",
            unique=True,
            postgresql_where=text("retry_idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    generation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("generations.id", ondelete="RESTRICT"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    runpod_job_id: Mapped[str | None] = mapped_column(String(255))
    output_object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    retry_idempotency_key: Mapped[str | None] = mapped_column(String(255))
    retry_request_fingerprint: Mapped[str | None] = mapped_column(String(64))
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    submission_attempts: Mapped[int] = mapped_column(Integer, default=0)
    poll_attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    queue_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    progress_stage: Mapped[str | None] = mapped_column(String(64))
    provider_status: Mapped[str | None] = mapped_column(String(32))
    provider_error: Mapped[str | None] = mapped_column(String(2000))
    worker_error_code: Mapped[str | None] = mapped_column(String(64))
    worker_error_stage: Mapped[str | None] = mapped_column(String(64))
    worker_error_retryable: Mapped[bool | None] = mapped_column(Boolean)
    worker_error_message: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
