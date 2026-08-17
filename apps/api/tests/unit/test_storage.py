import hashlib

import pytest

from app.core.config import Settings
from app.services.storage.s3 import S3StorageService


class FakeBody:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.closed = False

    def iter_chunks(self, chunk_size: int):
        del chunk_size
        yield self.content[:3]
        yield self.content[3:]

    def close(self) -> None:
        self.closed = True


class FakeClient:
    def __init__(self, content: bytes) -> None:
        self.body = FakeBody(content)

    def get_object(self, **kwargs):
        del kwargs
        return {"Body": self.body, "ContentLength": len(self.body.content)}


def storage(content: bytes) -> S3StorageService:
    service = object.__new__(S3StorageService)
    service.settings = Settings(
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
        AUTH_TOKEN_PEPPER="x" * 32,
        S3_ENDPOINT_URL="https://storage.example",
        S3_BUCKET="bucket",
        S3_ACCESS_KEY_ID="key",
        S3_SECRET_ACCESS_KEY="secret",
    )
    service.client = FakeClient(content)
    return service


@pytest.mark.parametrize("tamper", [False, True])
def test_output_checksum_verification(tamper: bool) -> None:
    content = b"generated-video"
    expected = hashlib.sha256(content).hexdigest()
    if tamper:
        expected = "0" * 64
    service = storage(content)
    if tamper:
        with pytest.raises(ValueError, match="OUTPUT_CHECKSUM_MISMATCH"):
            service._verify_object_checksum("output.mp4", expected, len(content), 100)
    else:
        service._verify_object_checksum("output.mp4", expected, len(content), 100)
