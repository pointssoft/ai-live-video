import asyncio
import logging
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import and_, or_, select, update

from app.api.dependencies import get_storage
from app.core.config import Settings, get_settings
from app.db.session import SessionFactory
from app.models import MediaAsset, MediaKind, MediaState
from app.services.media_validation import (
    MediaValidationError,
    ValidationResult,
    validate_motion,
    validate_portrait,
)

logger = logging.getLogger(__name__)


async def claim_next(settings: Settings, asset_id: uuid.UUID | None = None) -> MediaAsset | None:
    now = datetime.now(UTC)
    eligibility = [
        or_(
            MediaAsset.state == MediaState.UPLOADED.value,
            and_(
                MediaAsset.state == MediaState.VALIDATING.value,
                MediaAsset.validation_lease_expires_at < now,
            ),
        ),
        MediaAsset.validation_attempts < settings.MEDIA_VALIDATION_MAX_ATTEMPTS,
    ]
    if asset_id is not None:
        eligibility.append(MediaAsset.id == asset_id)
    async with SessionFactory() as db, db.begin():
        asset = (
            await db.execute(
                select(MediaAsset)
                .where(*eligibility)
                .order_by(MediaAsset.uploaded_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
        ).scalar_one_or_none()
        if asset is None:
            return None
        asset.state = MediaState.VALIDATING.value
        asset.validation_attempts += 1
        asset.validation_started_at = now
        asset.validation_lease_expires_at = now + timedelta(
            seconds=settings.MEDIA_VALIDATION_LEASE_SECONDS
        )
        asset.validation_lease_token = uuid.uuid4()
        asset.updated_at = now
        await db.flush()
        return asset


async def finish_success(asset: MediaAsset, result: ValidationResult) -> None:
    now = datetime.now(UTC)
    async with SessionFactory() as db, db.begin():
        await db.execute(
            update(MediaAsset)
            .where(
                MediaAsset.id == asset.id,
                MediaAsset.state == MediaState.VALIDATING.value,
                MediaAsset.validation_lease_token == asset.validation_lease_token,
            )
            .values(
                state=MediaState.READY.value,
                detected_content_type=result.detected_content_type,
                width=result.width,
                height=result.height,
                duration_ms=result.duration_ms,
                fps=result.fps,
                frame_count=result.frame_count,
                video_codec=result.video_codec,
                validated_at=now,
                ready_at=now,
                updated_at=now,
                validation_lease_expires_at=None,
                validation_lease_token=None,
                validation_error_code=None,
                validation_error_detail=None,
            )
        )


async def finish_failure(asset: MediaAsset, code: str, message: str) -> None:
    now = datetime.now(UTC)
    async with SessionFactory() as db, db.begin():
        await db.execute(
            update(MediaAsset)
            .where(
                MediaAsset.id == asset.id,
                MediaAsset.state == MediaState.VALIDATING.value,
                MediaAsset.validation_lease_token == asset.validation_lease_token,
            )
            .values(
                state=MediaState.VALIDATION_FAILED.value,
                validated_at=now,
                updated_at=now,
                validation_lease_expires_at=None,
                validation_lease_token=None,
                validation_error_code=code,
                validation_error_detail=message[:255],
            )
        )


async def finish_transient_failure(asset: MediaAsset) -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    exhausted = asset.validation_attempts >= settings.MEDIA_VALIDATION_MAX_ATTEMPTS
    async with SessionFactory() as db, db.begin():
        await db.execute(
            update(MediaAsset)
            .where(
                MediaAsset.id == asset.id,
                MediaAsset.state == MediaState.VALIDATING.value,
                MediaAsset.validation_lease_token == asset.validation_lease_token,
            )
            .values(
                state=(
                    MediaState.VALIDATION_FAILED.value if exhausted else MediaState.UPLOADED.value
                ),
                validated_at=now if exhausted else None,
                updated_at=now,
                validation_lease_expires_at=None,
                validation_lease_token=None,
                validation_error_code=("VALIDATION_TEMPORARILY_UNAVAILABLE" if exhausted else None),
                validation_error_detail=(
                    "Media validation could not be completed." if exhausted else None
                ),
            )
        )


async def process_one(
    settings: Settings | None = None, asset_id: uuid.UUID | None = None
) -> uuid.UUID | None:
    settings = settings or get_settings()
    asset = await claim_next(settings, asset_id)
    if asset is None:
        return None
    if asset.kind == MediaKind.PORTRAIT_ORIGINAL.value:
        max_bytes = settings.MAX_PORTRAIT_UPLOAD_BYTES
    elif asset.kind == MediaKind.MOTION_INPUT.value:
        max_bytes = settings.MAX_MOTION_UPLOAD_BYTES
    else:
        await finish_failure(asset, "MEDIA_KIND_UNSUPPORTED", "The media kind is unsupported.")
        return asset.id
    try:
        with tempfile.TemporaryDirectory(prefix="mimicmotion-validation-") as directory:
            path = Path(directory) / "source"
            downloaded = await get_storage().download_object(
                asset.object_key,
                path,
                expected_size=asset.size_bytes,
                max_bytes=max_bytes,
            )
            if downloaded.sha256 != asset.sha256:
                raise MediaValidationError(
                    "CHECKSUM_MISMATCH", "The uploaded file checksum does not match."
                )
            if asset.kind == MediaKind.PORTRAIT_ORIGINAL.value:
                result = await asyncio.to_thread(
                    validate_portrait, path, asset.content_type, settings
                )
            elif asset.kind == MediaKind.MOTION_INPUT.value:
                result = await validate_motion(path, asset.content_type, settings)
            else:
                raise MediaValidationError(
                    "MEDIA_KIND_UNSUPPORTED", "The media kind is unsupported."
                )
        await finish_success(asset, result)
    except MediaValidationError as exc:
        if exc.code == "VALIDATION_TEMPORARILY_UNAVAILABLE":
            await finish_transient_failure(asset)
        else:
            await finish_failure(asset, exc.code, exc.message)
    except ValueError as exc:
        code = str(exc) if str(exc).startswith("OBJECT_") else "MEDIA_INVALID"
        await finish_failure(asset, code, "The uploaded object is invalid.")
    except Exception as exc:
        logger.exception(
            "media_validation_transient_failure",
            extra={"asset_id": str(asset.id), "error_type": type(exc).__name__},
        )
        await finish_transient_failure(asset)
    return asset.id


async def run_forever() -> None:
    settings = get_settings()
    while True:
        processed = 0
        for _ in range(settings.MEDIA_VALIDATION_BATCH_SIZE):
            if await process_one(settings) is None:
                break
            processed += 1
        if processed == 0:
            await asyncio.sleep(settings.MEDIA_VALIDATION_POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(run_forever())
