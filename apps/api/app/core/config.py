from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_API_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_API_ROOT / ".env", extra="ignore", case_sensitive=True
    )

    APP_ENV: str = "local"
    LOG_LEVEL: str = "INFO"
    DATABASE_URL: str
    WEB_ALLOWED_ORIGINS: str = "http://localhost:3000"
    TRUSTED_HOSTS: str = "localhost,127.0.0.1"

    AUTH_TOKEN_PEPPER: str = Field(min_length=32)
    SESSION_COOKIE_NAME: str = "mm_session"
    SESSION_COOKIE_DOMAIN: str | None = None
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    SESSION_IDLE_TTL_SECONDS: int = 604800
    SESSION_ABSOLUTE_TTL_SECONDS: int = 2592000
    CSRF_COOKIE_NAME: str = "mm_csrf"
    CSRF_COOKIE_SECURE: bool = True
    CSRF_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    PASSWORD_MIN_LENGTH: int = 12

    S3_ENDPOINT_URL: str
    S3_REGION: str = "auto"
    S3_BUCKET: str
    S3_ACCESS_KEY_ID: str
    S3_SECRET_ACCESS_KEY: str
    S3_FORCE_PATH_STYLE: bool = False
    S3_PRESIGNED_UPLOAD_TTL_SECONDS: int = 900
    S3_PRESIGNED_DOWNLOAD_TTL_SECONDS: int = 300
    READY_CHECK_STORAGE: bool = True

    RUNPOD_API_KEY: str | None = None
    RUNPOD_ENDPOINT_ID: str | None = None
    RUNPOD_API_BASE_URL: str = "https://api.runpod.ai/v2"
    RUNPOD_REQUEST_TIMEOUT_SECONDS: int = 30
    GENERATION_SIGNED_URL_TTL_SECONDS: int = 7200
    GENERATION_LEASE_SECONDS: int = 60
    GENERATION_POLL_SECONDS: int = 5
    MAX_GENERATED_OUTPUT_BYTES: int = 200 * 1024 * 1024

    MAX_PORTRAIT_UPLOAD_BYTES: int = 15 * 1024 * 1024
    MAX_MOTION_UPLOAD_BYTES: int = 100 * 1024 * 1024
    DEFAULT_STORAGE_QUOTA_BYTES: int = 1024 * 1024 * 1024

    PORTRAIT_MIN_DIMENSION: int = 512
    PORTRAIT_MAX_DIMENSION: int = 8192
    PORTRAIT_MAX_PIXELS: int = 40_000_000
    MOTION_MIN_DURATION_MS: int = 5000
    MOTION_MAX_DURATION_MS: int = 15000
    MOTION_MAX_DIMENSION: int = 4096
    MEDIA_VALIDATION_TIMEOUT_SECONDS: int = 60
    MEDIA_VALIDATION_LEASE_SECONDS: int = 300
    MEDIA_VALIDATION_MAX_ATTEMPTS: int = 3
    MEDIA_VALIDATION_BATCH_SIZE: int = 4
    MEDIA_VALIDATION_POLL_SECONDS: int = 5

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @property
    def allowed_origins(self) -> list[str]:
        return [
            item.strip().rstrip("/") for item in self.WEB_ALLOWED_ORIGINS.split(",") if item.strip()
        ]

    @property
    def trusted_hosts(self) -> list[str]:
        return [item.strip() for item in self.TRUSTED_HOSTS.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
