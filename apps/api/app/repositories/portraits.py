import uuid
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MediaAsset, Portrait, PortraitStatus


async def get_asset_for_update(
    db: AsyncSession, asset_id: uuid.UUID, user_id: uuid.UUID
) -> MediaAsset | None:
    return (
        await db.execute(
            select(MediaAsset)
            .where(
                MediaAsset.id == asset_id,
                MediaAsset.user_id == user_id,
                MediaAsset.deleted_at.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()


async def get_by_original_asset(db: AsyncSession, asset_id: uuid.UUID) -> Portrait | None:
    return (
        await db.execute(select(Portrait).where(Portrait.original_asset_id == asset_id))
    ).scalar_one_or_none()


async def get_owned(
    db: AsyncSession,
    portrait_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    include_deleted: bool = False,
    for_update: bool = False,
) -> tuple[Portrait, MediaAsset] | None:
    conditions = [Portrait.id == portrait_id, Portrait.user_id == user_id]
    if not include_deleted:
        conditions.extend(
            [Portrait.deleted_at.is_(None), Portrait.status == PortraitStatus.READY.value]
        )
    statement = (
        select(Portrait, MediaAsset)
        .join(MediaAsset, MediaAsset.id == Portrait.original_asset_id)
        .where(*conditions)
    )
    if for_update:
        statement = statement.with_for_update()
    row = (await db.execute(statement)).one_or_none()
    return (row[0], row[1]) if row is not None else None


async def list_owned(
    db: AsyncSession,
    user_id: uuid.UUID,
    limit: int,
    cursor: tuple[datetime, uuid.UUID] | None,
) -> list[tuple[Portrait, MediaAsset]]:
    conditions = [
        Portrait.user_id == user_id,
        Portrait.status == PortraitStatus.READY.value,
        Portrait.deleted_at.is_(None),
    ]
    if cursor:
        created_at, portrait_id = cursor
        conditions.append(
            or_(
                Portrait.created_at < created_at,
                and_(Portrait.created_at == created_at, Portrait.id < portrait_id),
            )
        )
    rows = await db.execute(
        select(Portrait, MediaAsset)
        .join(MediaAsset, MediaAsset.id == Portrait.original_asset_id)
        .where(*conditions)
        .order_by(Portrait.created_at.desc(), Portrait.id.desc())
        .limit(limit + 1)
    )
    return list(rows.tuples())
