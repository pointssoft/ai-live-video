import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from app.api.dependencies import get_storage
from app.db.session import SessionFactory
from app.models import MediaAsset, MediaState


async def purge_batch(limit: int = 20) -> int:
    async with SessionFactory() as db:
        assets = list(
            (
                await db.scalars(
                    select(MediaAsset)
                    .where(
                        MediaAsset.state == MediaState.DELETED.value,
                        MediaAsset.purged_at.is_(None),
                    )
                    .with_for_update(skip_locked=True)
                    .limit(limit)
                )
            ).all()
        )
        purged = 0
        for asset in assets:
            try:
                await get_storage().delete_object(asset.object_key)
            except Exception:
                continue
            asset.purged_at = datetime.now(UTC)
            purged += 1
        await db.commit()
        return purged


if __name__ == "__main__":
    print(asyncio.run(purge_batch()))
