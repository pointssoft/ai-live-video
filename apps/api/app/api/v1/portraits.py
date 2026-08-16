import uuid

from fastapi import APIRouter, Query, Request, Response, status

from app.api.dependencies import CsrfProtected, CurrentUser, DbSession, Storage
from app.schemas.portraits import PortraitCreate, PortraitPage, PortraitResponse
from app.services import portrait_service

router = APIRouter(prefix="/portraits", tags=["portraits"])


@router.post("", response_model=PortraitResponse, status_code=status.HTTP_201_CREATED)
async def create_portrait(
    payload: PortraitCreate,
    request: Request,
    response: Response,
    user: CurrentUser,
    db: DbSession,
    storage: Storage,
    _csrf: CsrfProtected,
) -> PortraitResponse:
    result, created = await portrait_service.create_portrait(
        db, storage, user, payload.original_asset_id, request.state.request_id
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return result


@router.get("", response_model=PortraitPage)
async def list_portraits(
    user: CurrentUser,
    db: DbSession,
    storage: Storage,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> PortraitPage:
    return await portrait_service.list_portraits(db, storage, user, limit, cursor)


@router.get("/{portrait_id}", response_model=PortraitResponse)
async def get_portrait(
    portrait_id: uuid.UUID, user: CurrentUser, db: DbSession, storage: Storage
) -> PortraitResponse:
    return await portrait_service.get_portrait(db, storage, user, portrait_id)


@router.delete("/{portrait_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_portrait(
    portrait_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    storage: Storage,
    _csrf: CsrfProtected,
) -> None:
    await portrait_service.delete_portrait(db, storage, user, portrait_id, request.state.request_id)
