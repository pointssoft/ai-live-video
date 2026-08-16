from datetime import UTC, datetime

from fastapi import APIRouter, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import AppSettings, CsrfProtected, CurrentSession, DbSession
from app.auth.password import hash_password, verify_password
from app.auth.sessions import issue_csrf_token, issue_session_token, session_expiries
from app.core.errors import ApiError
from app.models import AuthSession, User, UserStatus
from app.schemas.auth import (
    AuthResponse,
    CsrfResponse,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def set_session_cookie(response: Response, raw_token: str, settings: AppSettings) -> None:
    response.set_cookie(
        settings.SESSION_COOKIE_NAME,
        raw_token,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        domain=settings.SESSION_COOKIE_DOMAIN or None,
        max_age=settings.SESSION_ABSOLUTE_TTL_SECONDS,
        path="/",
    )


def rotate_csrf(response: Response, settings: AppSettings) -> str:
    token = issue_csrf_token()
    response.set_cookie(
        settings.CSRF_COOKIE_NAME,
        token,
        httponly=False,
        secure=settings.CSRF_COOKIE_SECURE,
        samesite=settings.CSRF_COOKIE_SAMESITE,
        domain=settings.SESSION_COOKIE_DOMAIN or None,
        max_age=settings.SESSION_IDLE_TTL_SECONDS,
        path="/",
    )
    return token


@router.get("/csrf", response_model=CsrfResponse)
async def csrf(response: Response, settings: AppSettings) -> CsrfResponse:
    return CsrfResponse(csrf_token=rotate_csrf(response, settings))


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    response: Response,
    settings: AppSettings,
    db: DbSession,
    _csrf: CsrfProtected,
) -> AuthResponse:
    if len(payload.password) < settings.PASSWORD_MIN_LENGTH:
        raise ApiError(422, "PASSWORD_TOO_SHORT", "The password does not meet the minimum length.")
    now = datetime.now(UTC)
    user = User(
        email=str(payload.email).strip().lower(),
        password_hash=hash_password(payload.password),
        status=UserStatus.ACTIVE.value,
        storage_quota_bytes=settings.DEFAULT_STORAGE_QUOTA_BYTES,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ApiError(409, "ACCOUNT_EXISTS", "An account already exists for this email.") from exc
    raw_token, token_hash = issue_session_token(settings)
    idle_expiry, absolute_expiry = session_expiries(settings, now)
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=token_hash,
            created_at=now,
            last_seen_at=now,
            idle_expires_at=idle_expiry,
            absolute_expires_at=absolute_expiry,
            user_agent_hash=None,
            ip_prefix_hash=None,
        )
    )
    await db.commit()
    await db.refresh(user)
    set_session_cookie(response, raw_token, settings)
    rotate_csrf(response, settings)
    return AuthResponse(user=UserResponse.model_validate(user))


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    settings: AppSettings,
    db: DbSession,
    _csrf: CsrfProtected,
) -> AuthResponse:
    email = str(payload.email).strip().lower()
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        hash_password(payload.password)
        raise ApiError(401, "INVALID_CREDENTIALS", "The email or password is incorrect.")
    valid, replacement_hash = verify_password(user.password_hash, payload.password)
    if not valid or user.status != UserStatus.ACTIVE.value:
        raise ApiError(401, "INVALID_CREDENTIALS", "The email or password is incorrect.")
    if replacement_hash:
        user.password_hash = replacement_hash
    now = datetime.now(UTC)
    raw_token, token_hash = issue_session_token(settings)
    idle_expiry, absolute_expiry = session_expiries(settings, now)
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=token_hash,
            created_at=now,
            last_seen_at=now,
            idle_expires_at=idle_expiry,
            absolute_expires_at=absolute_expiry,
            user_agent_hash=None,
            ip_prefix_hash=None,
        )
    )
    await db.commit()
    set_session_cookie(response, raw_token, settings)
    rotate_csrf(response, settings)
    return AuthResponse(user=UserResponse.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    settings: AppSettings,
    db: DbSession,
    auth_session: CurrentSession,
    _csrf: CsrfProtected,
) -> None:
    auth_session.revoked_at = datetime.now(UTC)
    await db.commit()
    response.delete_cookie(
        settings.SESSION_COOKIE_NAME, domain=settings.SESSION_COOKIE_DOMAIN or None
    )
    response.delete_cookie(settings.CSRF_COOKIE_NAME, domain=settings.SESSION_COOKIE_DOMAIN or None)
