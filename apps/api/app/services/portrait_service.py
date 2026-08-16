import base64
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.models import AuditEvent, MediaAsset, MediaKind, MediaState, Portrait, PortraitStatus, User
from app.repositories import portraits as repository
from app.schemas.portraits import PortraitAssetResponse, PortraitPage, PortraitResponse
from app.services.storage import StorageService


def encode_cursor(portrait: Portrait) -> str:
    payload = json.dumps(
        {"created_at": portrait.created_at.isoformat(), "id": str(portrait.id)},
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
        portrait_id = uuid.UUID(payload["id"])
        if created_at.tzinfo is None:
            raise ValueError
        return created_at, portrait_id
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ApiError(422, "INVALID_CURSOR", "The pagination cursor is invalid.") from exc


async def response_for(
    portrait: Portrait, asset: MediaAsset, storage: StorageService
) -> PortraitResponse:
    if asset.width is None or asset.height is None or asset.detected_content_type is None:
        raise ApiError(500, "PORTRAIT_METADATA_MISSING", "Portrait metadata is unavailable.")
    signed = await storage.create_download_url(asset.object_key)
    return PortraitResponse(
        id=portrait.id,
        status=portrait.status,
        original_asset=PortraitAssetResponse(
            id=asset.id,
            content_type=asset.detected_content_type,
            size_bytes=asset.size_bytes,
            sha256=asset.sha256,
            width=asset.width,
            height=asset.height,
        ),
        image_url=signed.url,
        image_url_expires_at=signed.expires_at,
        created_at=portrait.created_at,
        updated_at=portrait.updated_at,
    )


async def create_portrait(
    db: AsyncSession,
    storage: StorageService,
    user: User,
    asset_id: uuid.UUID,
    request_id: str,
) -> tuple[PortraitResponse, bool]:
    asset = await repository.get_asset_for_update(db, asset_id, user.id)
    if asset is None:
        raise ApiError(404, "NOT_FOUND", "The portrait source was not found.")
    if asset.kind != MediaKind.PORTRAIT_ORIGINAL.value:
        raise ApiError(422, "PORTRAIT_ASSET_KIND_INVALID", "The selected media is not a portrait.")
    if asset.state != MediaState.READY.value:
        raise ApiError(409, "PORTRAIT_ASSET_NOT_READY", "The portrait has not passed validation.")
    existing = await repository.get_by_original_asset(db, asset.id)
    if existing:
        if existing.deleted_at is not None:
            raise ApiError(409, "PORTRAIT_DELETED", "This portrait was previously deleted.")
        return await response_for(existing, asset, storage), False
    now = datetime.now(UTC)
    portrait = Portrait(
        id=uuid.uuid4(),
        user_id=user.id,
        original_asset_id=asset.id,
        status=PortraitStatus.READY.value,
        created_at=now,
        updated_at=now,
    )
    db.add(portrait)
    db.add(
        AuditEvent(
            user_id=user.id,
            action="PORTRAIT_CREATED",
            resource_type="portrait",
            resource_id=portrait.id,
            request_id=request_id,
            metadata_json={},
            created_at=now,
        )
    )
    await db.commit()
    return await response_for(portrait, asset, storage), True


async def get_portrait(
    db: AsyncSession, storage: StorageService, user: User, portrait_id: uuid.UUID
) -> PortraitResponse:
    row = await repository.get_owned(db, portrait_id, user.id)
    if row is None:
        raise ApiError(404, "NOT_FOUND", "The portrait was not found.")
    return await response_for(*row, storage)


async def list_portraits(
    db: AsyncSession,
    storage: StorageService,
    user: User,
    limit: int,
    cursor_value: str | None,
) -> PortraitPage:
    rows = await repository.list_owned(db, user.id, limit, decode_cursor(cursor_value))
    has_more = len(rows) > limit
    selected = rows[:limit]
    items = [await response_for(portrait, asset, storage) for portrait, asset in selected]
    next_cursor = encode_cursor(selected[-1][0]) if has_more and selected else None
    return PortraitPage(items=items, next_cursor=next_cursor)


async def delete_portrait(
    db: AsyncSession,
    storage: StorageService,
    user: User,
    portrait_id: uuid.UUID,
    request_id: str,
) -> None:
    row = await repository.get_owned(
        db, portrait_id, user.id, include_deleted=True, for_update=True
    )
    if row is None:
        raise ApiError(404, "NOT_FOUND", "The portrait was not found.")
    portrait, asset = row
    if portrait.deleted_at is None:
        now = datetime.now(UTC)
        portrait.status = PortraitStatus.DELETED.value
        portrait.deleted_at = now
        portrait.updated_at = now
        asset.state = MediaState.DELETED.value
        asset.deleted_at = now
        asset.updated_at = now
        db.add(
            AuditEvent(
                user_id=user.id,
                action="PORTRAIT_DELETED",
                resource_type="portrait",
                resource_id=portrait.id,
                request_id=request_id,
                metadata_json={},
                created_at=now,
            )
        )
        await db.commit()
    if asset.purged_at is None:
        try:
            await storage.delete_object(asset.object_key)
        except Exception:
            return
        asset.purged_at = datetime.now(UTC)
        await db.commit()
