from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class PresignedRequest:
    url: str
    expires_at: datetime
    headers: dict[str, str]


@dataclass(frozen=True)
class ObjectMetadata:
    size_bytes: int
    content_type: str
    metadata: dict[str, str]
    etag: str | None


@dataclass(frozen=True)
class DownloadResult:
    size_bytes: int
    sha256: str


class StorageService(Protocol):
    async def create_upload_url(
        self, object_key: str, content_type: str, checksum: str
    ) -> PresignedRequest: ...

    async def create_download_url(
        self, object_key: str, *, expires_in_seconds: int | None = None
    ) -> PresignedRequest: ...

    async def create_output_upload_url(
        self,
        object_key: str,
        *,
        content_type: str,
        metadata: dict[str, str],
        expires_in_seconds: int,
    ) -> PresignedRequest: ...

    async def create_head_url(
        self, object_key: str, *, expires_in_seconds: int
    ) -> PresignedRequest: ...

    async def head_object(self, object_key: str) -> ObjectMetadata: ...

    async def download_object(
        self,
        object_key: str,
        destination: Path,
        *,
        expected_size: int,
        max_bytes: int,
    ) -> DownloadResult: ...

    async def delete_object(self, object_key: str) -> None: ...

    async def check_bucket_access(self) -> None: ...
