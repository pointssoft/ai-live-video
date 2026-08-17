import base64
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ApiError
from app.models import (
    AuditEvent,
    Generation,
    GenerationAttempt,
    GenerationAttemptStatus,
    GenerationStatus,
    MediaKind,
    MediaState,
    PortraitStatus,
    User,
)
from app.repositories import generations as repository
from app.schemas.generations import (
    GenerationExecutionResponse,
    GenerationOutputResponse,
    GenerationPage,
    GenerationResponse,
)
from app.services.generation_idempotency import (
    generation_request_fingerprint,
    retry_request_fingerprint,
    validate_idempotency_key,
)
from app.services.generation_lifecycle import (
    GENERATION_TERMINAL,
    transition_attempt,
    transition_generation,
)
from app.services.generation_payload import default_inference_parameters
from app.services.storage import StorageService


def retry_allowed(generation: Generation, attempt: GenerationAttempt) -> bool:
    return attempt.worker_error_retryable is True or (
        generation.status == GenerationStatus.TIMED_OUT.value
        and attempt.worker_error_code
        in {"RUNPOD_TIMED_OUT", "GENERATION_EXECUTION_TIMEOUT"}
    )


def encode_cursor(generation: Generation) -> str:
    payload = json.dumps(
        {"created_at": generation.created_at.isoformat(), "id": str(generation.id)},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(value: str | None) -> tuple[datetime, uuid.UUID] | None:
    if not value:
        return None
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        payload = json.loads(raw)
        created_at = datetime.fromisoformat(payload["created_at"])
        generation_id = uuid.UUID(payload["id"])
        if created_at.tzinfo is None:
            raise ValueError
        return created_at, generation_id
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ApiError(422, "INVALID_CURSOR", "The pagination cursor is invalid.") from exc


async def response_for(
    db: AsyncSession, storage: StorageService, generation: Generation
) -> GenerationResponse:
    attempt = await repository.get_current_attempt(db, generation.id)
    output = None
    if (
        generation.status == GenerationStatus.SUCCEEDED.value
        and generation.output_object_key
        and generation.output_content_type
        and generation.output_size_bytes is not None
        and generation.output_sha256
    ):
        signed = await storage.create_download_url(generation.output_object_key)
        output = GenerationOutputResponse(
            content_type=generation.output_content_type,
            size_bytes=generation.output_size_bytes,
            sha256=generation.output_sha256,
            download_url=signed.url,
            download_url_expires_at=signed.expires_at,
        )
    return GenerationResponse(
        id=generation.id,
        portrait_id=generation.portrait_id,
        motion_asset_id=generation.motion_asset_id,
        status=generation.status,
        execution=GenerationExecutionResponse(
            state=generation.status,
            attempt_id=attempt.id if attempt else None,
            provider_status=attempt.provider_status if attempt else None,
            progress_stage=attempt.progress_stage if attempt else None,
            failure_code=generation.failure_code,
            failure_message=generation.failure_message,
        ),
        output=output,
        created_at=generation.created_at,
        updated_at=generation.updated_at,
        started_at=generation.started_at,
        completed_at=generation.completed_at,
        failed_at=generation.failed_at,
        timed_out_at=generation.timed_out_at,
        canceled_at=generation.canceled_at,
    )


async def create_generation(
    db: AsyncSession,
    storage: StorageService,
    user: User,
    portrait_id: uuid.UUID,
    motion_asset_id: uuid.UUID,
    idempotency_key: str,
    request_id: str,
) -> tuple[GenerationResponse, bool]:
    validate_idempotency_key(idempotency_key)
    fingerprint = generation_request_fingerprint(portrait_id, motion_asset_id)
    existing = await repository.get_by_idempotency_key(db, user.id, idempotency_key)
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise ApiError(
                409,
                "IDEMPOTENCY_KEY_REUSED",
                "The idempotency key was already used for another request.",
            )
        return await response_for(db, storage, existing), True

    portrait, portrait_asset, motion = await repository.get_inputs_for_update(
        db, portrait_id, motion_asset_id, user.id
    )
    if portrait is None or portrait_asset is None:
        raise ApiError(404, "NOT_FOUND", "The portrait was not found.")
    if motion is None:
        raise ApiError(404, "NOT_FOUND", "The motion asset was not found.")
    if (
        portrait.status != PortraitStatus.READY.value
        or portrait.deleted_at is not None
        or portrait_asset.state != MediaState.READY.value
        or portrait_asset.deleted_at is not None
    ):
        raise ApiError(409, "PORTRAIT_NOT_READY", "The portrait is not available for generation.")
    if motion.kind != MediaKind.MOTION_INPUT.value:
        raise ApiError(
            422, "MOTION_ASSET_KIND_INVALID", "The selected media is not a motion input."
        )
    if motion.state != MediaState.READY.value or motion.deleted_at is not None:
        raise ApiError(409, "MOTION_ASSET_NOT_READY", "The motion input has not passed validation.")

    now = datetime.now(UTC)
    generation_id = uuid.uuid4()
    attempt_id = uuid.uuid4()
    generation = Generation(
        id=generation_id,
        user_id=user.id,
        portrait_id=portrait.id,
        motion_asset_id=motion.id,
        status=GenerationStatus.CREATED.value,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        created_at=now,
        updated_at=now,
    )
    attempt = GenerationAttempt(
        id=attempt_id,
        generation_id=generation_id,
        attempt_number=1,
        status=GenerationAttemptStatus.PENDING.value,
        output_object_key=(
            f"users/{user.id}/generations/{generation_id}/attempts/{attempt_id}/output.mp4"
        ),
        parameters_json=default_inference_parameters(),
        submission_attempts=0,
        poll_attempts=0,
        created_at=now,
        updated_at=now,
    )
    db.add_all([generation, attempt])
    db.add(
        AuditEvent(
            user_id=user.id,
            action="GENERATION_CREATED",
            resource_type="generation",
            resource_id=generation.id,
            request_id=request_id,
            metadata_json={
                "portrait_id": str(portrait.id),
                "motion_asset_id": str(motion.id),
                "attempt_id": str(attempt.id),
            },
            created_at=now,
        )
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await repository.get_by_idempotency_key(db, user.id, idempotency_key)
        if existing is None:
            raise
        if existing.request_fingerprint != fingerprint:
            raise ApiError(
                409,
                "IDEMPOTENCY_KEY_REUSED",
                "The idempotency key was already used for another request.",
            ) from None
        return await response_for(db, storage, existing), True
    return await response_for(db, storage, generation), False


async def retry_generation(
    db: AsyncSession,
    storage: StorageService,
    user: User,
    generation_id: uuid.UUID,
    idempotency_key: str,
    request_id: str,
) -> tuple[GenerationResponse, bool]:
    validate_idempotency_key(idempotency_key)
    fingerprint = retry_request_fingerprint(generation_id)
    current = await repository.get_current_attempt(db, generation_id, for_update=True)
    generation = await repository.get_owned(db, generation_id, user.id, for_update=True)
    if generation is None:
        raise ApiError(404, "NOT_FOUND", "The generation was not found.")
    existing = await repository.get_attempt_by_retry_key(
        db, generation.id, idempotency_key, for_update=True
    )
    if existing is not None:
        if existing.retry_request_fingerprint != fingerprint:
            raise ApiError(
                409,
                "IDEMPOTENCY_KEY_REUSED",
                "The retry idempotency key was already used for another request.",
            )
        return await response_for(db, storage, generation), True

    if generation.status not in {
        GenerationStatus.FAILED.value,
        GenerationStatus.TIMED_OUT.value,
    } or current is None or current.status not in GENERATION_TERMINAL:
        raise ApiError(
            409,
            "RETRY_NOT_ALLOWED",
            "This generation is not eligible for retry.",
        )
    if not retry_allowed(generation, current):
        raise ApiError(
            409,
            "RETRY_NOT_ALLOWED",
            "This generation failed for a non-retryable reason.",
        )
    settings = get_settings()
    if current.attempt_number >= settings.MAX_GENERATION_ATTEMPTS:
        raise ApiError(
            409,
            "RETRY_LIMIT_REACHED",
            "The generation retry limit has been reached.",
        )

    now = datetime.now(UTC)
    attempt_id = uuid.uuid4()
    attempt = GenerationAttempt(
        id=attempt_id,
        generation_id=generation.id,
        attempt_number=current.attempt_number + 1,
        status=GenerationAttemptStatus.PENDING.value,
        output_object_key=(
            f"users/{user.id}/generations/{generation.id}/attempts/{attempt_id}/output.mp4"
        ),
        retry_idempotency_key=idempotency_key,
        retry_request_fingerprint=fingerprint,
        parameters_json=dict(current.parameters_json),
        submission_attempts=0,
        poll_attempts=0,
        created_at=now,
        updated_at=now,
    )
    transition_generation(generation, GenerationStatus.CREATED.value)
    generation.failure_code = None
    generation.failure_message = None
    generation.failed_at = None
    generation.timed_out_at = None
    generation.updated_at = now
    db.add(attempt)
    db.add(
        AuditEvent(
            user_id=user.id,
            action="GENERATION_RETRY_CREATED",
            resource_type="generation",
            resource_id=generation.id,
            request_id=request_id,
            metadata_json={
                "previous_attempt_id": str(current.id),
                "attempt_id": str(attempt.id),
                "attempt_number": attempt.attempt_number,
            },
            created_at=now,
        )
    )
    await db.commit()
    return await response_for(db, storage, generation), False


async def get_generation(
    db: AsyncSession, storage: StorageService, user: User, generation_id: uuid.UUID
) -> GenerationResponse:
    generation = await repository.get_owned(db, generation_id, user.id)
    if generation is None:
        raise ApiError(404, "NOT_FOUND", "The generation was not found.")
    return await response_for(db, storage, generation)


async def list_generations(
    db: AsyncSession,
    storage: StorageService,
    user: User,
    limit: int,
    cursor_value: str | None,
) -> GenerationPage:
    rows = await repository.list_owned(db, user.id, limit, decode_cursor(cursor_value))
    has_more = len(rows) > limit
    selected = rows[:limit]
    return GenerationPage(
        items=[await response_for(db, storage, generation) for generation in selected],
        next_cursor=encode_cursor(selected[-1]) if has_more and selected else None,
    )


async def cancel_generation(
    db: AsyncSession,
    user: User,
    generation_id: uuid.UUID,
    request_id: str,
) -> None:
    attempt = await repository.get_current_attempt(db, generation_id, for_update=True)
    generation = await repository.get_owned(db, generation_id, user.id, for_update=True)
    if generation is None:
        raise ApiError(404, "NOT_FOUND", "The generation was not found.")
    if (
        generation.status in GENERATION_TERMINAL
        or generation.status == GenerationStatus.CANCEL_REQUESTED.value
    ):
        return

    now = datetime.now(UTC)
    if attempt and attempt.status == GenerationAttemptStatus.SUBMITTING.value:
        transition_generation(generation, GenerationStatus.CANCEL_REQUESTED.value)
    elif attempt and attempt.runpod_job_id:
        transition_generation(generation, GenerationStatus.CANCEL_REQUESTED.value)
        transition_attempt(attempt, GenerationAttemptStatus.CANCEL_REQUESTED.value)
    else:
        transition_generation(generation, GenerationStatus.CANCELED.value)
        generation.canceled_at = now
        if attempt:
            transition_attempt(attempt, GenerationAttemptStatus.CANCELED.value)
            attempt.finished_at = now
    generation.updated_at = now
    if attempt:
        attempt.updated_at = now
    db.add(
        AuditEvent(
            user_id=user.id,
            action="GENERATION_CANCELLATION_REQUESTED",
            resource_type="generation",
            resource_id=generation.id,
            request_id=request_id,
            metadata_json={},
            created_at=now,
        )
    )
    await db.commit()
