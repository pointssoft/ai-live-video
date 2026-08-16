from datetime import UTC, datetime

from app.auth.sessions import hash_session_token, issue_session_token, session_expiries
from app.core.config import Settings


def settings() -> Settings:
    return Settings(
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
        AUTH_TOKEN_PEPPER="p" * 32,
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_BUCKET="test",
        S3_ACCESS_KEY_ID="key",
        S3_SECRET_ACCESS_KEY="secret",
        SESSION_IDLE_TTL_SECONDS=60,
        SESSION_ABSOLUTE_TTL_SECONDS=120,
    )


def test_session_token_is_hashed_with_pepper() -> None:
    raw, digest = issue_session_token(settings())
    assert raw not in digest
    assert digest == hash_session_token(raw, "p" * 32)
    assert len(digest) == 64


def test_session_expiry_has_idle_and_absolute_limits() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    idle, absolute = session_expiries(settings(), now)
    assert (idle - now).total_seconds() == 60
    assert (absolute - now).total_seconds() == 120
