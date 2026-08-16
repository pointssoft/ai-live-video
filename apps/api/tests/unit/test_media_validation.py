from pathlib import Path

import pytest
from PIL import Image

from app.core.config import Settings
from app.services.media_validation import (
    MediaValidationError,
    detect_content_type,
    validate_portrait,
)


def settings() -> Settings:
    return Settings(
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
        AUTH_TOKEN_PEPPER="p" * 32,
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_BUCKET="test",
        S3_ACCESS_KEY_ID="key",
        S3_SECRET_ACCESS_KEY="secret",
    )


def test_valid_portrait_is_decoded(tmp_path: Path) -> None:
    path = tmp_path / "portrait.jpg"
    Image.new("RGB", (512, 640), color="blue").save(path, format="JPEG")
    assert detect_content_type(path) == "image/jpeg"
    result = validate_portrait(path, "image/jpeg", settings())
    assert (result.width, result.height) == (512, 640)


def test_portrait_mime_mismatch_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "portrait.png"
    Image.new("RGB", (512, 512), color="blue").save(path, format="PNG")
    with pytest.raises(MediaValidationError, match="does not match") as caught:
        validate_portrait(path, "image/jpeg", settings())
    assert caught.value.code == "MEDIA_TYPE_MISMATCH"


def test_undersized_portrait_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "portrait.webp"
    Image.new("RGB", (511, 700), color="blue").save(path, format="WEBP")
    with pytest.raises(MediaValidationError) as caught:
        validate_portrait(path, "image/webp", settings())
    assert caught.value.code == "PORTRAIT_TOO_SMALL"
