import uuid
from datetime import UTC, datetime

from app.models import Generation, GenerationAttempt
from app.services.generation_lifecycle import (
    ATTEMPT_TERMINAL,
    GENERATION_TERMINAL,
    transition_attempt,
    transition_generation,
)
from app.tasks.generation_orchestration import (
    progress_stage,
    provider_error_details,
    sanitized_provider_error,
)


def test_provider_progress_prefers_known_worker_stage() -> None:
    assert progress_stage("IN_PROGRESS", "RUNNING_INFERENCE") == "RUNNING_INFERENCE"
    assert progress_stage("IN_QUEUE", None) == "WAITING_FOR_GPU"
    assert progress_stage("IN_PROGRESS", "provider-private-value") == "GENERATING"


def test_provider_error_is_sanitized_and_structured() -> None:
    error = {
        "error": {
            "code": "MEDIA_VALIDATION_FAILED",
            "stage": "VALIDATING_MEDIA",
            "retryable": False,
            "message": "Input rejected",
            "secret": "must-not-be-persisted",
        }
    }
    code, stage, retryable, message = provider_error_details(error)
    assert (code, stage, retryable, message) == (
        "MEDIA_VALIDATION_FAILED",
        "VALIDATING_MEDIA",
        False,
        "Input rejected",
    )
    stored = sanitized_provider_error(error, default_code="RUNPOD_EXECUTION_FAILED")
    assert "must-not-be-persisted" not in stored
    assert "MEDIA_VALIDATION_FAILED" in stored


def test_timeout_states_are_terminal() -> None:
    assert "TIMED_OUT" in GENERATION_TERMINAL
    assert "TIMED_OUT" in ATTEMPT_TERMINAL


def test_queued_and_running_can_timeout() -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    item = Generation(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        portrait_id=uuid.uuid4(),
        motion_asset_id=uuid.uuid4(),
        status="QUEUED",
        created_at=now,
        updated_at=now,
    )
    attempt = GenerationAttempt(
        id=uuid.uuid4(),
        generation_id=item.id,
        attempt_number=1,
        status="QUEUED",
        output_object_key="users/u/generations/g/attempts/a/output.mp4",
        submission_attempts=0,
        poll_attempts=0,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
    transition_generation(item, "TIMED_OUT")
    transition_attempt(attempt, "TIMED_OUT")
    assert item.status == "TIMED_OUT"
    assert attempt.status == "TIMED_OUT"
