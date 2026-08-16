import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import Settings
from app.core.errors import ApiError
from app.models import Generation, GenerationAttempt, MediaAsset
from app.schemas.generations import GenerationCreate
from app.services.generation_idempotency import (
    generation_request_fingerprint,
    validate_idempotency_key,
)
from app.services.generation_lifecycle import (
    InvalidGenerationTransition,
    transition_generation,
)
from app.services.generation_payload import WorkerResult, build_worker_input
from app.services.generation_service import decode_cursor, encode_cursor


def generation() -> Generation:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    return Generation(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        portrait_id=uuid.uuid4(),
        motion_asset_id=uuid.uuid4(),
        status="CREATED",
        created_at=now,
        updated_at=now,
    )


def settings() -> Settings:
    return Settings(
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
        AUTH_TOKEN_PEPPER="x" * 32,
        S3_ENDPOINT_URL="https://storage.example",
        S3_BUCKET="bucket",
        S3_ACCESS_KEY_ID="key",
        S3_SECRET_ACCESS_KEY="secret",
    )


class FakeStorage:
    async def create_download_url(self, key: str, *, expires_in_seconds: int | None = None):
        return type(
            "Signed",
            (),
            {
                "url": f"https://storage.example/{key}",
                "expires_at": datetime.now(UTC) + timedelta(seconds=expires_in_seconds or 300),
                "headers": {},
            },
        )()

    async def create_output_upload_url(self, key: str, **kwargs):
        metadata = kwargs["metadata"]
        return type(
            "Signed",
            (),
            {
                "url": f"https://storage.example/{key}?put=1",
                "expires_at": datetime.now(UTC) + timedelta(hours=2),
                "headers": {
                    "content-type": "video/mp4",
                    "x-amz-meta-generation-id": metadata["generation-id"],
                    "x-amz-meta-attempt-id": metadata["attempt-id"],
                },
            },
        )()

    async def create_head_url(self, key: str, **kwargs):
        return type(
            "Signed",
            (),
            {
                "url": f"https://storage.example/{key}?head=1",
                "expires_at": datetime.now(UTC) + timedelta(hours=2),
                "headers": {},
            },
        )()


def asset(user_id: uuid.UUID, key: str, content_type: str) -> MediaAsset:
    now = datetime.now(UTC)
    return MediaAsset(
        id=uuid.uuid4(),
        user_id=user_id,
        kind="MOTION_INPUT",
        object_key=key,
        content_type=content_type,
        detected_content_type=content_type,
        size_bytes=10,
        sha256="a" * 64,
        state="READY",
        validation_attempts=1,
        upload_expires_at=now,
        created_at=now,
        updated_at=now,
    )


def test_generation_cursor_round_trip() -> None:
    item = generation()
    assert decode_cursor(encode_cursor(item)) == (item.created_at, item.id)


def test_invalid_generation_cursor_is_rejected() -> None:
    with pytest.raises(ApiError) as caught:
        decode_cursor("not-a-valid-cursor")
    assert caught.value.code == "INVALID_CURSOR"


def test_generation_create_forbids_unknown_fields() -> None:
    with pytest.raises(ValueError):
        GenerationCreate.model_validate(
            {
                "portrait_id": str(uuid.uuid4()),
                "motion_asset_id": str(uuid.uuid4()),
                "provider_job_id": "not-accepted",
            }
        )


async def test_worker_payload_is_strict_and_versioned() -> None:
    item = generation()
    attempt = GenerationAttempt(
        id=uuid.uuid4(),
        generation_id=item.id,
        attempt_number=1,
        status="PENDING",
        output_object_key=(
            f"users/{item.user_id}/generations/{item.id}/attempts/test/output.mp4"
        ),
        submission_attempts=0,
        poll_attempts=0,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
    portrait = asset(item.user_id, "users/u/uploads/p/source.jpg", "image/jpeg")
    motion = asset(item.user_id, "users/u/uploads/m/source.mp4", "video/mp4")
    payload = await build_worker_input(settings(), FakeStorage(), item, attempt, portrait, motion)
    assert payload["schema_version"] == "1.0"
    assert payload["generation_id"] == str(item.id)
    assert payload["attempt_id"] == str(attempt.id)
    assert payload["output"]["object_key"] == attempt.output_object_key  # type: ignore[index]


def test_generation_fingerprint_is_stable_and_input_sensitive() -> None:
    portrait_id = uuid.uuid4()
    motion_id = uuid.uuid4()
    first = generation_request_fingerprint(portrait_id, motion_id)
    assert first == generation_request_fingerprint(portrait_id, motion_id)
    assert first != generation_request_fingerprint(uuid.uuid4(), motion_id)
    assert first != generation_request_fingerprint(portrait_id, uuid.uuid4())


@pytest.mark.parametrize("value", ["", "has space", "line\nbreak", "é", "x" * 256])
def test_invalid_idempotency_keys_are_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="IDEMPOTENCY_KEY_INVALID"):
        validate_idempotency_key(value)


def test_generation_terminal_transition_is_rejected() -> None:
    item = generation()
    item.status = "SUCCEEDED"
    with pytest.raises(InvalidGenerationTransition):
        transition_generation(item, "RUNNING")


def test_generation_transition_is_idempotent() -> None:
    item = generation()
    transition_generation(item, "CREATED")
    assert item.status == "CREATED"


def test_worker_result_rejects_wrong_checksum() -> None:
    with pytest.raises(ValueError):
        WorkerResult.model_validate(
            {
                "schema_version": "1.0",
                "generation_id": str(uuid.uuid4()),
                "attempt_id": str(uuid.uuid4()),
                "status": "completed",
                "output": {
                    "object_key": "users/u/generations/g/attempts/a/output.mp4",
                    "sha256": "invalid",
                    "content_type": "video/mp4",
                    "size_bytes": 10,
                },
            }
        )
