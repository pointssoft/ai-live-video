import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import or_, select

from app.core.config import Settings, get_settings
from app.db.session import SessionFactory
from app.models import (
    Generation,
    GenerationAttempt,
    GenerationAttemptStatus,
    GenerationStatus,
    MediaAsset,
    MediaKind,
    MediaState,
    Portrait,
    PortraitStatus,
)
from app.services.generation_lifecycle import (
    ATTEMPT_TERMINAL,
    GENERATION_TERMINAL,
    transition_attempt,
    transition_generation,
)
from app.services.generation_payload import WorkerResult, build_worker_input
from app.services.runpod import RunpodClient, RunpodService, RunpodStatusResult
from app.services.storage import StorageService


async def claim_submission(settings: Settings) -> tuple[uuid.UUID, uuid.UUID] | None:
    now = datetime.now(UTC)
    async with SessionFactory() as db, db.begin():
        attempt = (
            await db.execute(
                select(GenerationAttempt)
                .join(Generation, Generation.id == GenerationAttempt.generation_id)
                .where(
                    GenerationAttempt.status == GenerationAttemptStatus.PENDING.value,
                    Generation.status == GenerationStatus.CREATED.value,
                )
                .order_by(GenerationAttempt.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
        ).scalar_one_or_none()
        if attempt is None:
            return None
        transition_attempt(attempt, GenerationAttemptStatus.SUBMITTING.value)
        attempt.submission_attempts += 1
        lease_token = uuid.uuid4()
        attempt.lease_token = lease_token
        attempt.lease_expires_at = now + timedelta(seconds=settings.GENERATION_LEASE_SECONDS)
        attempt.updated_at = now
        return attempt.id, lease_token


async def load_submission(
    attempt_id: uuid.UUID,
) -> tuple[Generation, GenerationAttempt, MediaAsset, MediaAsset] | None:
    async with SessionFactory() as db:
        row = (
            await db.execute(
                select(Generation, GenerationAttempt, MediaAsset)
                .join(GenerationAttempt, GenerationAttempt.generation_id == Generation.id)
                .join(Portrait, Portrait.id == Generation.portrait_id)
                .join(MediaAsset, MediaAsset.id == Portrait.original_asset_id)
                .where(
                    GenerationAttempt.id == attempt_id,
                    GenerationAttempt.status == GenerationAttemptStatus.SUBMITTING.value,
                    Generation.status.in_(
                        [
                            GenerationStatus.CREATED.value,
                            GenerationStatus.CANCEL_REQUESTED.value,
                        ]
                    ),
                    Portrait.status == PortraitStatus.READY.value,
                    Portrait.deleted_at.is_(None),
                    MediaAsset.state == MediaState.READY.value,
                    MediaAsset.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        if row is None:
            return None
        generation, attempt, portrait_asset = row
        motion = (
            await db.execute(
                select(MediaAsset).where(
                    MediaAsset.id == generation.motion_asset_id,
                    MediaAsset.user_id == generation.user_id,
                    MediaAsset.kind == MediaKind.MOTION_INPUT.value,
                    MediaAsset.state == MediaState.READY.value,
                    MediaAsset.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if motion is None:
            return None
        return generation, attempt, portrait_asset, motion


async def finish_submission(
    attempt_id: uuid.UUID,
    lease_token: uuid.UUID,
    job_id: str,
    provider_status: str,
    settings: Settings,
) -> None:
    now = datetime.now(UTC)
    async with SessionFactory() as db, db.begin():
        attempt = await db.get(GenerationAttempt, attempt_id, with_for_update=True)
        if (
            attempt is None
            or attempt.status != GenerationAttemptStatus.SUBMITTING.value
            or attempt.lease_token != lease_token
        ):
            return
        generation = await db.get(Generation, attempt.generation_id, with_for_update=True)
        if generation is None or generation.status not in {
            GenerationStatus.CREATED.value,
            GenerationStatus.CANCEL_REQUESTED.value,
        }:
            return
        attempt.runpod_job_id = job_id
        attempt.provider_status = provider_status
        attempt.submitted_at = now
        attempt.next_poll_at = now + timedelta(seconds=settings.GENERATION_POLL_SECONDS)
        attempt.lease_token = None
        attempt.lease_expires_at = None
        attempt.updated_at = now
        if generation.status == GenerationStatus.CANCEL_REQUESTED.value:
            transition_attempt(attempt, GenerationAttemptStatus.CANCEL_REQUESTED.value)
            attempt.next_poll_at = now
        else:
            transition_attempt(attempt, GenerationAttemptStatus.QUEUED.value)
            transition_generation(generation, GenerationStatus.QUEUED.value)
        generation.updated_at = now


async def fail_attempt(
    attempt_id: uuid.UUID,
    code: str,
    message: str,
    lease_token: uuid.UUID | None = None,
) -> None:
    now = datetime.now(UTC)
    async with SessionFactory() as db, db.begin():
        attempt = await db.get(GenerationAttempt, attempt_id, with_for_update=True)
        if attempt is None or (lease_token is not None and attempt.lease_token != lease_token):
            return
        generation = await db.get(Generation, attempt.generation_id, with_for_update=True)
        if (
            generation is None
            or attempt.status in ATTEMPT_TERMINAL
            or generation.status in GENERATION_TERMINAL
        ):
            return
        transition_attempt(attempt, GenerationAttemptStatus.FAILED.value)
        attempt.worker_error_code = code
        attempt.worker_error_message = message[:255]
        attempt.finished_at = now
        attempt.updated_at = now
        attempt.lease_token = None
        attempt.lease_expires_at = None
        attempt.next_poll_at = None
        transition_generation(generation, GenerationStatus.FAILED.value)
        generation.failure_code = code
        generation.failure_message = message[:255]
        generation.failed_at = now
        generation.updated_at = now


async def mark_submission_unknown(
    attempt_id: uuid.UUID, lease_token: uuid.UUID
) -> None:
    now = datetime.now(UTC)
    async with SessionFactory() as db, db.begin():
        attempt = await db.get(GenerationAttempt, attempt_id, with_for_update=True)
        if (
            attempt is None
            or attempt.status != GenerationAttemptStatus.SUBMITTING.value
            or attempt.lease_token != lease_token
        ):
            return
        generation = await db.get(Generation, attempt.generation_id, with_for_update=True)
        if generation is None or generation.status in GENERATION_TERMINAL:
            return
        transition_attempt(attempt, GenerationAttemptStatus.SUBMISSION_UNKNOWN.value)
        attempt.worker_error_code = "RUNPOD_SUBMISSION_UNKNOWN"
        attempt.worker_error_message = "The provider submission result is unknown."
        attempt.finished_at = now
        attempt.updated_at = now
        attempt.lease_token = None
        attempt.lease_expires_at = None
        attempt.next_poll_at = None
        transition_generation(generation, GenerationStatus.FAILED.value)
        generation.failure_code = "RUNPOD_SUBMISSION_UNKNOWN"
        generation.failure_message = "The provider submission result could not be determined."
        generation.failed_at = now
        generation.updated_at = now


async def cancel_unsubmitted_claim(
    attempt_id: uuid.UUID, lease_token: uuid.UUID
) -> None:
    now = datetime.now(UTC)
    async with SessionFactory() as db, db.begin():
        attempt = await db.get(GenerationAttempt, attempt_id, with_for_update=True)
        if (
            attempt is None
            or attempt.status != GenerationAttemptStatus.SUBMITTING.value
            or attempt.lease_token != lease_token
        ):
            return
        generation = await db.get(Generation, attempt.generation_id, with_for_update=True)
        if generation is None or generation.status != GenerationStatus.CANCEL_REQUESTED.value:
            return
        transition_attempt(attempt, GenerationAttemptStatus.CANCELED.value)
        attempt.finished_at = now
        attempt.updated_at = now
        attempt.lease_token = None
        attempt.lease_expires_at = None
        transition_generation(generation, GenerationStatus.CANCELED.value)
        generation.canceled_at = now
        generation.updated_at = now


async def submit_one(
    settings: Settings, storage: StorageService, runpod: RunpodService
) -> uuid.UUID | None:
    claimed = await claim_submission(settings)
    if claimed is None:
        return None
    attempt_id, lease_token = claimed
    loaded = await load_submission(attempt_id)
    if loaded is None:
        await fail_attempt(
            attempt_id,
            "INPUTS_NOT_READY",
            "Generation inputs are unavailable.",
            lease_token,
        )
        return attempt_id
    generation, attempt, portrait, motion = loaded
    if generation.status == GenerationStatus.CANCEL_REQUESTED.value:
        await cancel_unsubmitted_claim(attempt.id, lease_token)
        return attempt_id
    try:
        worker_input = await build_worker_input(
            settings, storage, generation, attempt, portrait, motion
        )
        result = await runpod.submit(worker_input)
        await finish_submission(
            attempt.id, lease_token, result.job_id, result.status, settings
        )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        await fail_attempt(
            attempt.id,
            "RUNPOD_SUBMISSION_FAILED",
            "The generation provider could not be reached.",
            lease_token,
        )
    except (httpx.ReadTimeout, httpx.WriteTimeout):
        await mark_submission_unknown(attempt.id, lease_token)
    except Exception:
        await fail_attempt(
            attempt.id,
            "RUNPOD_SUBMISSION_FAILED",
            "Generation submission failed.",
            lease_token,
        )
    return attempt_id


async def apply_status(
    attempt_id: uuid.UUID,
    result: RunpodStatusResult,
    settings: Settings,
    storage: StorageService,
) -> None:
    now = datetime.now(UTC)
    async with SessionFactory() as db, db.begin():
        attempt = await db.get(GenerationAttempt, attempt_id, with_for_update=True)
        if attempt is None:
            return
        generation = await db.get(Generation, attempt.generation_id, with_for_update=True)
        if generation is None:
            return
        if attempt.status in ATTEMPT_TERMINAL or generation.status in GENERATION_TERMINAL:
            return
        if attempt.runpod_job_id != result.job_id:
            raise ValueError("RUNPOD_JOB_ID_MISMATCH")
        cancel_requested = (
            attempt.status == GenerationAttemptStatus.CANCEL_REQUESTED.value
            or generation.status == GenerationStatus.CANCEL_REQUESTED.value
        )
        attempt.provider_status = result.status
        attempt.poll_attempts += 1
        attempt.updated_at = now
        if result.status == "IN_QUEUE":
            if not cancel_requested and attempt.status != GenerationAttemptStatus.RUNNING.value:
                transition_attempt(attempt, GenerationAttemptStatus.QUEUED.value)
                if generation.status != GenerationStatus.RUNNING.value:
                    transition_generation(generation, GenerationStatus.QUEUED.value)
            attempt.next_poll_at = now + timedelta(seconds=settings.GENERATION_POLL_SECONDS)
        elif result.status == "IN_PROGRESS":
            if not cancel_requested:
                transition_attempt(attempt, GenerationAttemptStatus.RUNNING.value)
                transition_generation(generation, GenerationStatus.RUNNING.value)
                attempt.started_at = attempt.started_at or now
                generation.started_at = generation.started_at or now
            attempt.next_poll_at = now + timedelta(seconds=settings.GENERATION_POLL_SECONDS)
        elif result.status == "COMPLETED":
            worker = WorkerResult.model_validate(result.output)
            if (
                worker.schema_version != "1.0"
                or worker.status != "completed"
                or worker.generation_id != generation.id
                or worker.attempt_id != attempt.id
                or worker.output.object_key != attempt.output_object_key
                or worker.output.content_type != "video/mp4"
                or worker.output.size_bytes > settings.MAX_GENERATED_OUTPUT_BYTES
            ):
                raise ValueError("WORKER_RESULT_INVALID")
            metadata = await storage.head_object(attempt.output_object_key)
            if (
                metadata.size_bytes != worker.output.size_bytes
                or metadata.content_type != "video/mp4"
                or metadata.metadata.get("generation-id") != str(generation.id)
                or metadata.metadata.get("attempt-id") != str(attempt.id)
            ):
                raise ValueError("OUTPUT_VERIFICATION_FAILED")
            transition_attempt(attempt, GenerationAttemptStatus.SUCCEEDED.value)
            attempt.finished_at = now
            attempt.next_poll_at = None
            transition_generation(generation, GenerationStatus.SUCCEEDED.value)
            generation.output_object_key = worker.output.object_key
            generation.output_content_type = worker.output.content_type
            generation.output_size_bytes = worker.output.size_bytes
            generation.output_sha256 = worker.output.sha256
            generation.completed_at = now
        elif result.status in {"FAILED", "TIMED_OUT"}:
            transition_attempt(attempt, GenerationAttemptStatus.FAILED.value)
            attempt.provider_error = str(result.error)[:2000]
            attempt.finished_at = now
            attempt.next_poll_at = None
            transition_generation(generation, GenerationStatus.FAILED.value)
            generation.failure_code = f"RUNPOD_{result.status}"
            generation.failure_message = "Generation execution failed."
            generation.failed_at = now
        elif result.status == "CANCELLED":
            transition_attempt(attempt, GenerationAttemptStatus.CANCELED.value)
            attempt.finished_at = now
            attempt.next_poll_at = None
            transition_generation(generation, GenerationStatus.CANCELED.value)
            generation.canceled_at = now
        else:
            attempt.next_poll_at = now + timedelta(seconds=settings.GENERATION_POLL_SECONDS)
        attempt.lease_token = None
        attempt.lease_expires_at = None
        generation.updated_at = now


async def reconcile_one(
    settings: Settings, storage: StorageService, runpod: RunpodService
) -> uuid.UUID | None:
    now = datetime.now(UTC)
    async with SessionFactory() as db, db.begin():
        attempt = (
            await db.execute(
                select(GenerationAttempt)
                .where(
                    GenerationAttempt.status.in_(
                        [
                            GenerationAttemptStatus.QUEUED.value,
                            GenerationAttemptStatus.RUNNING.value,
                            GenerationAttemptStatus.CANCEL_REQUESTED.value,
                        ]
                    ),
                    or_(
                        GenerationAttempt.next_poll_at.is_(None),
                        GenerationAttempt.next_poll_at <= now,
                    ),
                    or_(
                        GenerationAttempt.lease_expires_at.is_(None),
                        GenerationAttempt.lease_expires_at < now,
                    ),
                )
                .order_by(GenerationAttempt.next_poll_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
        ).scalar_one_or_none()
        if attempt is None or attempt.runpod_job_id is None:
            return None
        attempt_id = attempt.id
        job_id = attempt.runpod_job_id
        cancel_requested = attempt.status == GenerationAttemptStatus.CANCEL_REQUESTED.value
        attempt.lease_token = uuid.uuid4()
        attempt.lease_expires_at = now + timedelta(seconds=settings.GENERATION_LEASE_SECONDS)

    try:
        if cancel_requested:
            await runpod.cancel(job_id)
        result = await runpod.status(job_id)
        await apply_status(attempt_id, result, settings, storage)
    except ValueError as exc:
        await fail_attempt(attempt_id, str(exc), "The worker result could not be verified.")
    except Exception:
        async with SessionFactory() as db, db.begin():
            current = await db.get(GenerationAttempt, attempt_id, with_for_update=True)
            if current:
                current.next_poll_at = datetime.now(UTC) + timedelta(
                    seconds=settings.GENERATION_POLL_SECONDS
                )
                current.lease_token = None
                current.lease_expires_at = None
    return attempt_id


async def run_forever() -> None:
    from app.api.dependencies import get_storage

    settings = get_settings()
    if not settings.RUNPOD_API_KEY or not settings.RUNPOD_ENDPOINT_ID:
        raise RuntimeError("Runpod orchestration is not configured")
    storage = get_storage()
    runpod = RunpodClient(settings)
    while True:
        submitted = await submit_one(settings, storage, runpod)
        reconciled = await reconcile_one(settings, storage, runpod)
        if submitted is None and reconciled is None:
            await asyncio.sleep(settings.GENERATION_POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(run_forever())
