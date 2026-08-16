from app.core.config import Settings


def test_railway_database_url_uses_asyncpg() -> None:
    settings = Settings(
        DATABASE_URL="postgresql://user:pass@host/db",
        AUTH_TOKEN_PEPPER="p" * 32,
        S3_ENDPOINT_URL="https://example.invalid",
        S3_BUCKET="bucket",
        S3_ACCESS_KEY_ID="key",
        S3_SECRET_ACCESS_KEY="secret",
        WEB_ALLOWED_ORIGINS="https://app.example.com, http://localhost:3000/",
    )
    assert settings.DATABASE_URL.startswith("postgresql+asyncpg://")
    assert settings.allowed_origins == ["https://app.example.com", "http://localhost:3000"]
