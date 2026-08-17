"""phase 2a execution hardening

Revision ID: 0007_phase2a_execution_hardening
Revises: 0006_generation_idempotency
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_phase2a_execution_hardening"
down_revision: str | None = "0006_generation_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_generations_status", "generations", type_="check")
    op.create_check_constraint(
        "ck_generations_status",
        "generations",
        "status IN ('CREATED', 'QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', "
        "'TIMED_OUT', 'CANCEL_REQUESTED', 'CANCELED')",
    )
    op.add_column(
        "generations", sa.Column("timed_out_at", sa.DateTime(timezone=True))
    )

    op.drop_constraint("ck_generation_attempts_status", "generation_attempts", type_="check")
    op.create_check_constraint(
        "ck_generation_attempts_status",
        "generation_attempts",
        "status IN ('PENDING', 'SUBMITTING', 'QUEUED', 'RUNNING', 'SUCCEEDED', "
        "'FAILED', 'TIMED_OUT', 'CANCEL_REQUESTED', 'CANCELED', 'SUBMISSION_UNKNOWN')",
    )
    for _name, column in (
        ("queue_deadline_at", sa.Column("queue_deadline_at", sa.DateTime(timezone=True))),
        (
            "execution_deadline_at",
            sa.Column("execution_deadline_at", sa.DateTime(timezone=True)),
        ),
        ("progress_stage", sa.Column("progress_stage", sa.String(64))),
    ):
        op.add_column("generation_attempts", column)


def downgrade() -> None:
    op.execute(
        "UPDATE generation_attempts SET status = 'FAILED' WHERE status = 'TIMED_OUT'"
    )
    op.execute("UPDATE generations SET status = 'FAILED' WHERE status = 'TIMED_OUT'")
    for name in ("progress_stage", "execution_deadline_at", "queue_deadline_at"):
        op.drop_column("generation_attempts", name)
    op.drop_constraint("ck_generation_attempts_status", "generation_attempts", type_="check")
    op.create_check_constraint(
        "ck_generation_attempts_status",
        "generation_attempts",
        "status IN ('PENDING', 'SUBMITTING', 'QUEUED', 'RUNNING', 'SUCCEEDED', "
        "'FAILED', 'CANCEL_REQUESTED', 'CANCELED', 'SUBMISSION_UNKNOWN')",
    )
    op.drop_column("generations", "timed_out_at")
    op.drop_constraint("ck_generations_status", "generations", type_="check")
    op.create_check_constraint(
        "ck_generations_status",
        "generations",
        "status IN ('CREATED', 'QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', "
        "'CANCEL_REQUESTED', 'CANCELED')",
    )
