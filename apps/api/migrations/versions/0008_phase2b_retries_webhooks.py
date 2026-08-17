"""phase 2b retries and webhook inbox

Revision ID: 0008_phase2b_retries_webhooks
Revises: 0007_phase2a_execution_hardening
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_phase2b_retries_webhooks"
down_revision: str | None = "0007_phase2a_execution_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "generation_attempts",
        sa.Column("retry_idempotency_key", sa.String(255)),
    )
    op.add_column(
        "generation_attempts",
        sa.Column("retry_request_fingerprint", sa.String(64)),
    )
    op.add_column(
        "generation_attempts",
        sa.Column("parameters_json", postgresql.JSONB()),
    )
    op.execute(
        """
        UPDATE generation_attempts
        SET parameters_json = '{
            "profile": "mimicmotion-v1.1-balanced-v1",
            "profile_revision": 1,
            "model_version": "v1.1",
            "resolution": 576,
            "tile_size": 72,
            "tile_overlap": 6,
            "num_inference_steps": 25,
            "noise_aug_strength": 0.0,
            "guidance_scale": 2.0,
            "sample_stride": 2,
            "output_fps": 15,
            "seed": 42
        }'::jsonb
        WHERE parameters_json IS NULL
        """
    )
    op.alter_column("generation_attempts", "parameters_json", nullable=False)
    op.create_check_constraint(
        "ck_generation_attempt_retry_idempotency_pair",
        "generation_attempts",
        "(retry_idempotency_key IS NULL AND retry_request_fingerprint IS NULL) OR "
        "(retry_idempotency_key IS NOT NULL AND retry_request_fingerprint IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_generation_attempt_retry_fingerprint",
        "generation_attempts",
        "retry_request_fingerprint IS NULL OR "
        "retry_request_fingerprint ~ '^[0-9a-f]{64}$'",
    )
    op.create_index(
        "uq_generation_attempt_retry_key",
        "generation_attempts",
        ["generation_id", "retry_idempotency_key"],
        unique=True,
        postgresql_where=sa.text("retry_idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "runpod_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False, server_default="runpod"),
        sa.Column("provider_event_id", sa.String(255)),
        sa.Column("runpod_job_id", sa.String(255), nullable=False),
        sa.Column("dedupe_key", sa.String(128), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("provider_status", sa.String(32), nullable=False),
        sa.Column("authentication_verified", sa.Boolean(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("processing_lease_token", postgresql.UUID(as_uuid=True)),
        sa.Column("processing_lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("processing_error", sa.String(255)),
        sa.UniqueConstraint("dedupe_key", name="uq_runpod_webhook_dedupe_key"),
    )
    op.create_index(
        "ix_runpod_webhook_job_received",
        "runpod_webhook_events",
        ["runpod_job_id", "received_at"],
    )
    op.create_index(
        "ix_runpod_webhook_unprocessed",
        "runpod_webhook_events",
        ["processed_at", "received_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_runpod_webhook_unprocessed", table_name="runpod_webhook_events")
    op.drop_index("ix_runpod_webhook_job_received", table_name="runpod_webhook_events")
    op.drop_table("runpod_webhook_events")
    op.drop_index("uq_generation_attempt_retry_key", table_name="generation_attempts")
    op.drop_constraint(
        "ck_generation_attempt_retry_fingerprint", "generation_attempts", type_="check"
    )
    op.drop_constraint(
        "ck_generation_attempt_retry_idempotency_pair", "generation_attempts", type_="check"
    )
    op.alter_column("generation_attempts", "parameters_json", nullable=True)
    op.drop_column("generation_attempts", "parameters_json")
    op.drop_column("generation_attempts", "retry_request_fingerprint")
    op.drop_column("generation_attempts", "retry_idempotency_key")
