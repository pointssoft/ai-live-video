"""generation execution lifecycle

Revision ID: 0005_generation_execution
Revises: 0004_generations
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_generation_execution"
down_revision: str | None = "0004_generations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_generations_status", "generations", type_="check")
    op.create_check_constraint(
        "ck_generations_status",
        "generations",
        "status IN ('CREATED', 'QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', "
        "'CANCEL_REQUESTED', 'CANCELED')",
    )
    for _name, column in (
        ("output_object_key", sa.Column("output_object_key", sa.String(512))),
        ("output_content_type", sa.Column("output_content_type", sa.String(100))),
        ("output_size_bytes", sa.Column("output_size_bytes", sa.BigInteger())),
        ("output_sha256", sa.Column("output_sha256", sa.String(64))),
        ("failure_code", sa.Column("failure_code", sa.String(64))),
        ("failure_message", sa.Column("failure_message", sa.String(255))),
        ("started_at", sa.Column("started_at", sa.DateTime(timezone=True))),
        ("completed_at", sa.Column("completed_at", sa.DateTime(timezone=True))),
        ("failed_at", sa.Column("failed_at", sa.DateTime(timezone=True))),
    ):
        op.add_column("generations", column)
    op.create_index(
        "ix_generations_status_updated", "generations", ["status", "updated_at", "id"]
    )
    op.create_table(
        "generation_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "generation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("generations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("runpod_job_id", sa.String(255)),
        sa.Column("output_object_key", sa.String(512), nullable=False),
        sa.Column("submission_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("poll_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_token", postgresql.UUID(as_uuid=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("next_poll_at", sa.DateTime(timezone=True)),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("provider_status", sa.String(32)),
        sa.Column("provider_error", sa.String(2000)),
        sa.Column("worker_error_code", sa.String(64)),
        sa.Column("worker_error_stage", sa.String(64)),
        sa.Column("worker_error_retryable", sa.Boolean()),
        sa.Column("worker_error_message", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempt_number >= 1", name="ck_generation_attempt_number"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'SUBMITTING', 'QUEUED', 'RUNNING', 'SUCCEEDED', "
            "'FAILED', 'CANCEL_REQUESTED', 'CANCELED', 'SUBMISSION_UNKNOWN')",
            name="ck_generation_attempts_status",
        ),
        sa.UniqueConstraint(
            "generation_id", "attempt_number", name="uq_generation_attempt_number"
        ),
        sa.UniqueConstraint("runpod_job_id", name="uq_generation_attempt_runpod_job"),
    )
    op.create_index(
        "ix_generation_attempt_claim",
        "generation_attempts",
        ["status", "next_poll_at", "lease_expires_at"],
    )
    op.create_index(
        "ix_generation_attempt_generation",
        "generation_attempts",
        ["generation_id", "attempt_number"],
    )


def downgrade() -> None:
    op.drop_table("generation_attempts")
    op.drop_index("ix_generations_status_updated", table_name="generations")
    for name in (
        "failed_at",
        "completed_at",
        "started_at",
        "failure_message",
        "failure_code",
        "output_sha256",
        "output_size_bytes",
        "output_content_type",
        "output_object_key",
    ):
        op.drop_column("generations", name)
    op.drop_constraint("ck_generations_status", "generations", type_="check")
    op.create_check_constraint(
        "ck_generations_status", "generations", "status IN ('CREATED', 'CANCELED')"
    )
