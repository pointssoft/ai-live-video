from fastapi import APIRouter

from app.api.dependencies import CurrentUser
from app.schemas.auth import UserResponse

router = APIRouter(tags=["users"])


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
