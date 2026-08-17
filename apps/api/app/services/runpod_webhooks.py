import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import RunpodWebhookEvent
from app.repositories import generations as repository
from app.schemas.webhooks import RunpodWebhookPayload
from app.services.runpod import RunpodService
from app.services.storage import StorageService


async def _get_or_create_event(
    db: AsyncSession,
    payload: RunpodWebhookPayload,
    payload_hash: str,
    dedupe_key: str,
) -> RunpodWebhookEvent:
    event = await db.scalar(
        select(RunpodWebhookEvent).where(
            RunpodWebhookEvent.dedupe_key == dedupe_key
        )
    )
    if event is not None:
        return event
    event = RunpodWebhookEvent(
        id=uuid.uuid4(),
        provider="runpod",
        provider_event_id=payload.event_id,
        runpod_job_id=payload.runpod_job_id,
        dedupe_key=dedupe_key,
        payload_hash=payload_hash,
        provider_status=payload.status,
        authentication_verified=True,
        received_at=datetime.now(UTC),
    )
    db.add(event)
    try:
        await db.commit()
        return event
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(
            select(RunpodWebhookEvent).where(
                RunpodWebhookEvent.dedupe_key == dedupe_key
            )
        )
        if existing is None:
            raise
        return existing


async def _finish_event(
    db: AsyncSession,
    event_id: uuid.UUID,
    lease_token: uuid.UUID,
    *,
    processed: bool,
    error: str | None,
) -> None:
    event = await db.scalar(
        select(RunpodWebhookEvent)
        .where(RunpodWebhookEvent.id == event_id)
        .with_for_update()
    )
    if event is None or event.processing_lease_token != lease_token:
        await db.rollback()
        return
    event.processing_error = error
    event.processed_at = datetime.now(UTC) if processed else None
    event.processing_lease_token = None
    event.processing_lease_expires_at = None
    await db.commit()


async def ingest_runpod_webhook(
    db: AsyncSession,
    storage: StorageService,
    settings: Settings,
    runpod: RunpodService,
    payload: RunpodWebhookPayload,
    raw_body: bytes,
) -> bool:
    payload_hash = hashlib.sha256(raw_body).hexdigest()
    dedupe_material = (
        f"event:{payload.event_id}"
        if payload.event_id
        else f"payload:{payload.runpod_job_id}:{payload.status}:{payload_hash}"
    )
    dedupe_key = hashlib.sha256(dedupe_material.encode()).hexdigest()
    event = await _get_or_create_event(db, payload, payload_hash, dedupe_key)

    now = datetime.now(UTC)
    claimed = await db.scalar(
        select(RunpodWebhookEvent)
        .where(RunpodWebhookEvent.id == event.id)
        .with_for_update()
    )
    if claimed is None:
        await db.rollback()
        return False
    if claimed.processed_at is not None:
        await db.rollback()
        return True
    if (
        claimed.processing_lease_expires_at is not None
        and claimed.processing_lease_expires_at > now
    ):
        await db.rollback()
        return True
    lease_token = uuid.uuid4()
    claimed.processing_lease_token = lease_token
    claimed.processing_lease_expires_at = now + timedelta(
        seconds=settings.RUNPOD_WEBHOOK_LEASE_SECONDS
    )
    claimed.processing_error = None
    await db.commit()

    attempt = await repository.get_attempt_by_runpod_job_id(db, payload.runpod_job_id)
    if attempt is None:
        await _finish_event(
            db,
            event.id,
            lease_token,
            processed=False,
            error="UNKNOWN_RUNPOD_JOB_ID",
        )
        return False

    try:
        from app.tasks.generation_orchestration import apply_status

        result = await runpod.status(payload.runpod_job_id)
        await apply_status(attempt.id, result, settings, storage)
    except Exception as exc:
        detail = str(exc)[:220] or "webhook processing failed"
        await _finish_event(
            db,
            event.id,
            lease_token,
            processed=False,
            error=f"{type(exc).__name__}: {detail}"[:255],
        )
        return False

    await _finish_event(
        db,
        event.id,
        lease_token,
        processed=True,
        error=None,
    )
    return True
