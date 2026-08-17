import asyncio
from datetime import UTC, datetime

from sqlalchemy import or_, select

from app.api.dependencies import get_storage
from app.db.session import SessionFactory
from app.models import Generation


async def purge_batch(limit: int = 20) -> int:
    now = datetime.now(UTC)
    async with SessionFactory() as db:
        generations = list(
            (
                await db.scalars(
                    select(Generation)
                    .where(
                        Generation.deleted_at.is_not(None),
                        Generation.output_purged_at.is_(None),
                        or_(
                            Generation.purge_after_at.is_(None),
                            Generation.purge_after_at <= now,
                        ),
                    )
                    .with_for_update(skip_locked=True)
                    .limit(limit)
                )
            ).all()
        )
        purged = 0
        for generation in generations:
            if generation.output_object_key:
                try:
                    await get_storage().delete_object(generation.output_object_key)
                except Exception:
                    continue
            generation.output_purged_at = datetime.now(UTC)
            purged += 1
        await db.commit()
        return purged


if __name__ == "__main__":
    print(asyncio.run(purge_batch()))
