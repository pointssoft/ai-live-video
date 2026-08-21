import uuid
from datetime import UTC, datetime

from botocore.exceptions import ClientError
from fastapi import APIRouter, status
from sqlalchemy import func, select

from app.api.dependencies import CsrfProtected, CurrentUser, DbSession, Storage
from app.core.config import get_settings
from app.core.errors import ApiError
from app.models import MediaAsset, MediaKind, MediaState, User
from app.schemas.uploads import UploadCreate, UploadResponse, UploadSessionResponse

router = APIRouter(prefix="/uploads", tags=["uploads"])

_CONTENT_TYPES = {
    MediaKind.PORTRAIT_ORIGINAL.value: {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    },
    MediaKind.MOTION_INPUT.value: {
        "video/webm": "webm",
        "video/mp4": "mp4",
    },
}


@router.post("", response_model=UploadSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_upload(
    payload: UploadCreate,
    user: CurrentUser,
    db: DbSession,
    storage: Storage,
    _csrf: CsrfProtected,
) -> UploadSessionResponse:
    settings = get_settings()
    extension = _CONTENT_TYPES[payload.kind.value].get(payload.content_type)
    if not extension:
        raise ApiError(422, "MEDIA_TYPE_NOT_ALLOWED", "This media type is not supported.")
    max_bytes = (
        settings.MAX_PORTRAIT_UPLOAD_BYTES
        if payload.kind.value == MediaKind.PORTRAIT_ORIGINAL.value
        else settings.MAX_MOTION_UPLOAD_BYTES
    )
    if payload.size_bytes > max_bytes:
        raise ApiError(413, "UPLOAD_TOO_LARGE", "The selected file is too large.")
    locked_user = (
        await db.execute(select(User).where(User.id == user.id).with_for_update())
    ).scalar_one()
    used = (
        await db.scalar(
            select(func.coalesce(func.sum(MediaAsset.size_bytes), 0)).where(
                MediaAsset.user_id == user.id,
                MediaAsset.state.in_(
                    [
                        MediaState.UPLOADING.value,
                        MediaState.UPLOADED.value,
                        MediaState.VALIDATING.value,
                        MediaState.READY.value,
                    ]
                ),
            )
        )
        or 0
    )
    if used + payload.size_bytes > locked_user.storage_quota_bytes:
        raise ApiError(409, "STORAGE_QUOTA_EXCEEDED", "Your storage quota has been reached.")
    asset_id = uuid.uuid4()
    object_key = f"users/{user.id}/uploads/{asset_id}/source.{extension}"
    presigned = await storage.create_upload_url(object_key, payload.content_type, payload.sha256)
    now = datetime.now(UTC)
    asset = MediaAsset(
        id=asset_id,
        user_id=user.id,
        kind=payload.kind.value,
        object_key=object_key,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        sha256=payload.sha256,
        state=MediaState.UPLOADING.value,
        upload_expires_at=presigned.expires_at,
        created_at=now,
        updated_at=now,
    )
    db.add(asset)
    await db.commit()
    return UploadSessionResponse(
        upload_id=asset.id,
        state=asset.state,
        object_key=asset.object_key,
        upload_url=presigned.url,
        expires_at=presigned.expires_at,
        required_headers=presigned.headers,
    )


async def owned_asset(asset_id: uuid.UUID, user: User, db: DbSession) -> MediaAsset:
    asset = (
        await db.execute(
            select(MediaAsset).where(
                MediaAsset.id == asset_id,
                MediaAsset.user_id == user.id,
                MediaAsset.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if asset is None:
        raise ApiError(404, "NOT_FOUND", "The upload was not found.")
    return asset


@router.get("/{asset_id}", response_model=UploadResponse)
async def get_upload(asset_id: uuid.UUID, user: CurrentUser, db: DbSession) -> UploadResponse:
    return UploadResponse.model_validate(await owned_asset(asset_id, user, db))


@router.post(
    "/{asset_id}/complete", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED
)
async def complete_upload(
    asset_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    storage: Storage,
    _csrf: CsrfProtected,
) -> UploadResponse:
    asset = await owned_asset(asset_id, user, db)
    terminal_or_processing = {
        MediaState.UPLOADED.value,
        MediaState.VALIDATING.value,
        MediaState.READY.value,
        MediaState.VALIDATION_FAILED.value,
    }
    if asset.state in terminal_or_processing:
        return UploadResponse.model_validate(asset)
    now = datetime.now(UTC)
    if asset.state != MediaState.UPLOADING.value or asset.upload_expires_at < now:
        if asset.state == MediaState.UPLOADING.value:
            asset.state = MediaState.UPLOAD_EXPIRED.value
            asset.updated_at = now
            await db.commit()
        raise ApiError(409, "UPLOAD_EXPIRED", "This upload session has expired.")
    try:
        metadata = await storage.head_object(asset.object_key)
    except ClientError as exc:
        error_code = str(exc.response.get("Error", {}).get("Code", ""))
        if error_code in {"404", "NoSuchKey", "NotFound"}:
            raise ApiError(
                409, "UPLOAD_INCOMPLETE", "The object has not finished uploading."
            ) from exc
        raise ApiError(
            503, "STORAGE_UNAVAILABLE", "Storage verification is temporarily unavailable."
        ) from exc
    if (
        metadata.size_bytes != asset.size_bytes
        or metadata.content_type != asset.content_type
        or metadata.metadata.get("sha256") != asset.sha256
    ):
        raise ApiError(409, "UPLOAD_METADATA_MISMATCH", "The uploaded object metadata is invalid.")
    locked_asset = (
        await db.execute(
            select(MediaAsset)
            .where(MediaAsset.id == asset.id, MediaAsset.user_id == user.id)
            .with_for_update()
        )
    ).scalar_one()
    if locked_asset.state == MediaState.UPLOADING.value:
        locked_asset.state = MediaState.READY.value
        locked_asset.detected_content_type = locked_asset.content_type
        locked_asset.provider_etag = metadata.etag
        locked_asset.uploaded_at = now
        locked_asset.ready_at = now
        locked_asset.updated_at = now
        await db.commit()
    return UploadResponse.model_validate(locked_asset)
