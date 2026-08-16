import hmac
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth.sessions import hash_session_token
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.session import get_db
from app.models import AuthSession, User, UserStatus
from app.services.storage import S3StorageService, StorageService

DbSession = Annotated[AsyncSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


@lru_cache
def get_storage() -> S3StorageService:
    return S3StorageService(get_settings())


async def require_csrf(request: Request, settings: AppSettings) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    header = request.headers.get("X-CSRF-Token", "")
    cookie = request.cookies.get(settings.CSRF_COOKIE_NAME, "")
    if not header or not cookie or not hmac.compare_digest(header, cookie):
        raise ApiError(403, "CSRF_INVALID", "The request security token is invalid.")
    origin = request.headers.get("Origin")
    if origin and origin.rstrip("/") not in settings.allowed_origins:
        raise ApiError(403, "ORIGIN_NOT_ALLOWED", "The request origin is not allowed.")


async def get_current_session(
    request: Request,
    settings: AppSettings,
    db: DbSession,
) -> AuthSession:
    session_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not session_token:
        raise ApiError(401, "AUTH_REQUIRED", "Authentication is required.")
    token_hash = hash_session_token(session_token, settings.AUTH_TOKEN_PEPPER)
    result = await db.execute(
        select(AuthSession)
        .options(joinedload(AuthSession.user))
        .where(AuthSession.token_hash == token_hash)
    )
    auth_session = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if (
        auth_session is None
        or auth_session.revoked_at is not None
        or auth_session.idle_expires_at <= now
        or auth_session.absolute_expires_at <= now
        or auth_session.user.status != UserStatus.ACTIVE.value
    ):
        raise ApiError(401, "AUTH_REQUIRED", "Authentication is required.")
    auth_session.last_seen_at = now
    auth_session.idle_expires_at = min(
        now + timedelta(seconds=settings.SESSION_IDLE_TTL_SECONDS),
        auth_session.absolute_expires_at,
    )
    await db.commit()
    return auth_session


CurrentSession = Annotated[AuthSession, Depends(get_current_session)]


async def get_current_user(auth_session: CurrentSession) -> User:
    return auth_session.user


CurrentUser = Annotated[User, Depends(get_current_user)]
CsrfProtected = Annotated[None, Depends(require_csrf)]
Storage = Annotated[StorageService, Depends(get_storage)]
