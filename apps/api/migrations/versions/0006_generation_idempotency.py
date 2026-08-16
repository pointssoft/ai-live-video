"""generation idempotency and attempt invariants

Revision ID: 0006_generation_idempotency
Revises: 0005_generation_execution
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_generation_idempotency"
down_revision: str | None = "0005_generation_execution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("generations", sa.Column("idempotency_key", sa.String(255)))
    op.add_column("generations", sa.Column("request_fingerprint", sa.String(64)))
    op.create_check_constraint(
        "ck_generations_idempotency_pair",
        "generations",
        "(idempotency_key IS NULL AND request_fingerprint IS NULL) OR "
        "(idempotency_key IS NOT NULL AND request_fingerprint IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_generations_request_fingerprint",
        "generations",
        "request_fingerprint IS NULL OR request_fingerprint ~ '^[0-9a-f]{64}$'",
    )
    op.create_index(
        "uq_generations_user_idempotency_key",
        "generations",
        ["user_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_check_constraint(
        "ck_generation_attempt_counters",
        "generation_attempts",
        "submission_attempts >= 0 AND poll_attempts >= 0",
    )
    op.create_check_constraint(
        "ck_generation_attempt_submission_unknown",
        "generation_attempts",
        "status <> 'SUBMISSION_UNKNOWN' OR "
        "(runpod_job_id IS NULL AND finished_at IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_generation_attempt_submission_unknown", "generation_attempts", type_="check"
    )
    op.drop_constraint(
        "ck_generation_attempt_counters", "generation_attempts", type_="check"
    )
    op.drop_index("uq_generations_user_idempotency_key", table_name="generations")
    op.drop_constraint("ck_generations_request_fingerprint", "generations", type_="check")
    op.drop_constraint("ck_generations_idempotency_pair", "generations", type_="check")
    op.drop_column("generations", "request_fingerprint")
    op.drop_column("generations", "idempotency_key")
