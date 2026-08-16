import uuid
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Generation, GenerationAttempt, MediaAsset, Portrait


async def get_inputs_for_update(
    db: AsyncSession,
    portrait_id: uuid.UUID,
    motion_asset_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[Portrait | None, MediaAsset | None, MediaAsset | None]:
    portrait_row = (
        await db.execute(
            select(Portrait, MediaAsset)
            .join(MediaAsset, MediaAsset.id == Portrait.original_asset_id)
            .where(Portrait.id == portrait_id, Portrait.user_id == user_id)
            .with_for_update()
        )
    ).one_or_none()
    motion = (
        await db.execute(
            select(MediaAsset)
            .where(MediaAsset.id == motion_asset_id, MediaAsset.user_id == user_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if portrait_row is None:
        return None, None, motion
    return portrait_row[0], portrait_row[1], motion


async def get_by_idempotency_key(
    db: AsyncSession,
    user_id: uuid.UUID,
    idempotency_key: str,
    *,
    for_update: bool = False,
) -> Generation | None:
    statement = select(Generation).where(
        Generation.user_id == user_id,
        Generation.idempotency_key == idempotency_key,
    )
    if for_update:
        statement = statement.with_for_update()
    return (await db.execute(statement)).scalar_one_or_none()


async def get_owned(
    db: AsyncSession,
    generation_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Generation | None:
    statement = select(Generation).where(
        Generation.id == generation_id, Generation.user_id == user_id
    )
    if for_update:
        statement = statement.with_for_update()
    return (await db.execute(statement)).scalar_one_or_none()


async def list_owned(
    db: AsyncSession,
    user_id: uuid.UUID,
    limit: int,
    cursor: tuple[datetime, uuid.UUID] | None,
) -> list[Generation]:
    conditions = [Generation.user_id == user_id]
    if cursor:
        created_at, generation_id = cursor
        conditions.append(
            or_(
                Generation.created_at < created_at,
                and_(Generation.created_at == created_at, Generation.id < generation_id),
            )
        )
    result = await db.execute(
        select(Generation)
        .where(*conditions)
        .order_by(Generation.created_at.desc(), Generation.id.desc())
        .limit(limit + 1)
    )
    return list(result.scalars())


async def get_current_attempt(
    db: AsyncSession, generation_id: uuid.UUID, *, for_update: bool = False
) -> GenerationAttempt | None:
    statement = (
        select(GenerationAttempt)
        .where(GenerationAttempt.generation_id == generation_id)
        .order_by(GenerationAttempt.attempt_number.desc())
        .limit(1)
    )
    if for_update:
        statement = statement.with_for_update()
    return (await db.execute(statement)).scalar_one_or_none()
