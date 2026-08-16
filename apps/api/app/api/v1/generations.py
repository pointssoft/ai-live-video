import uuid

from fastapi import APIRouter, Header, Query, Request, Response, status

from app.api.dependencies import CsrfProtected, CurrentUser, DbSession, Storage
from app.core.errors import ApiError
from app.schemas.generations import GenerationCreate, GenerationPage, GenerationResponse
from app.services import generation_service

router = APIRouter(prefix="/generations", tags=["generations"])


@router.post("", response_model=GenerationResponse, status_code=status.HTTP_201_CREATED)
async def create_generation(
    payload: GenerationCreate,
    request: Request,
    response: Response,
    user: CurrentUser,
    db: DbSession,
    storage: Storage,
    _csrf: CsrfProtected,
    idempotency_key: str = Header(..., alias="Idempotency-Key", max_length=255),
) -> GenerationResponse:
    try:
        result, replayed = await generation_service.create_generation(
            db,
            storage,
            user,
            payload.portrait_id,
            payload.motion_asset_id,
            idempotency_key,
            request.state.request_id,
        )
    except ValueError as exc:
        if str(exc) == "IDEMPOTENCY_KEY_INVALID":
            raise ApiError(
                422, "IDEMPOTENCY_KEY_INVALID", "The idempotency key is invalid."
            ) from exc
        raise
    if replayed:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotency-Replayed"] = "true"
    return result


@router.get("", response_model=GenerationPage)
async def list_generations(
    user: CurrentUser,
    db: DbSession,
    storage: Storage,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> GenerationPage:
    return await generation_service.list_generations(db, storage, user, limit, cursor)


@router.get("/{generation_id}", response_model=GenerationResponse)
async def get_generation(
    generation_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    storage: Storage,
) -> GenerationResponse:
    return await generation_service.get_generation(db, storage, user, generation_id)


@router.delete("/{generation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_generation(
    generation_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    _csrf: CsrfProtected,
) -> None:
    await generation_service.cancel_generation(
        db, user, generation_id, request.state.request_id
    )
