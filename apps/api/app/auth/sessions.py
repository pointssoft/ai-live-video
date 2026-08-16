import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from app.core.config import Settings


def issue_session_token(settings: Settings) -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    return raw, hash_session_token(raw, settings.AUTH_TOKEN_PEPPER)


def hash_session_token(raw: str, pepper: str) -> str:
    return hashlib.sha256(f"{pepper}{raw}".encode()).hexdigest()


def session_expiries(settings: Settings, now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(UTC)
    return (
        now + timedelta(seconds=settings.SESSION_IDLE_TTL_SECONDS),
        now + timedelta(seconds=settings.SESSION_ABSOLUTE_TTL_SECONDS),
    )


def issue_csrf_token() -> str:
    return secrets.token_urlsafe(32)
