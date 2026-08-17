import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import boto3
from botocore.client import Config

from app.core.config import Settings
from app.services.storage.base import DownloadResult, ObjectMetadata, PresignedRequest


class S3StorageService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            region_name=settings.S3_REGION,
            aws_access_key_id=settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path" if settings.S3_FORCE_PATH_STYLE else "virtual"},
            ),
        )

    async def create_upload_url(
        self, object_key: str, content_type: str, checksum: str
    ) -> PresignedRequest:
        params = {
            "Bucket": self.settings.S3_BUCKET,
            "Key": object_key,
            "ContentType": content_type,
            "Metadata": {"sha256": checksum},
        }
        url = await asyncio.to_thread(
            self.client.generate_presigned_url,
            "put_object",
            Params=params,
            ExpiresIn=self.settings.S3_PRESIGNED_UPLOAD_TTL_SECONDS,
        )
        return PresignedRequest(
            url=url,
            expires_at=datetime.now(UTC)
            + timedelta(seconds=self.settings.S3_PRESIGNED_UPLOAD_TTL_SECONDS),
            headers={"content-type": content_type, "x-amz-meta-sha256": checksum},
        )

    async def create_download_url(
        self, object_key: str, *, expires_in_seconds: int | None = None
    ) -> PresignedRequest:
        ttl = expires_in_seconds or self.settings.S3_PRESIGNED_DOWNLOAD_TTL_SECONDS
        url = await asyncio.to_thread(
            self.client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self.settings.S3_BUCKET, "Key": object_key},
            ExpiresIn=ttl,
        )
        return PresignedRequest(
            url=url,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
            headers={},
        )

    async def create_output_upload_url(
        self,
        object_key: str,
        *,
        content_type: str,
        metadata: dict[str, str],
        expires_in_seconds: int,
    ) -> PresignedRequest:
        params = {
            "Bucket": self.settings.S3_BUCKET,
            "Key": object_key,
            "ContentType": content_type,
            "Metadata": metadata,
        }
        url = await asyncio.to_thread(
            self.client.generate_presigned_url,
            "put_object",
            Params=params,
            ExpiresIn=expires_in_seconds,
        )
        headers = {"content-type": content_type}
        headers.update({f"x-amz-meta-{key}": value for key, value in metadata.items()})
        return PresignedRequest(
            url=url,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in_seconds),
            headers=headers,
        )

    async def create_head_url(
        self, object_key: str, *, expires_in_seconds: int
    ) -> PresignedRequest:
        url = await asyncio.to_thread(
            self.client.generate_presigned_url,
            "head_object",
            Params={"Bucket": self.settings.S3_BUCKET, "Key": object_key},
            ExpiresIn=expires_in_seconds,
        )
        return PresignedRequest(
            url=url,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in_seconds),
            headers={},
        )

    async def head_object(self, object_key: str) -> ObjectMetadata:
        response = await asyncio.to_thread(
            self.client.head_object, Bucket=self.settings.S3_BUCKET, Key=object_key
        )
        return ObjectMetadata(
            size_bytes=response["ContentLength"],
            content_type=response.get("ContentType", "application/octet-stream"),
            metadata=response.get("Metadata", {}),
            etag=response.get("ETag", "").strip('"') or None,
        )

    async def verify_object_checksum(
        self,
        object_key: str,
        *,
        expected_sha256: str,
        expected_size: int,
        max_bytes: int,
    ) -> None:
        await asyncio.to_thread(
            self._verify_object_checksum,
            object_key,
            expected_sha256,
            expected_size,
            max_bytes,
        )

    def _verify_object_checksum(
        self, object_key: str, expected_sha256: str, expected_size: int, max_bytes: int
    ) -> None:
        response = self.client.get_object(Bucket=self.settings.S3_BUCKET, Key=object_key)
        body = response["Body"]
        declared_size = int(response["ContentLength"])
        if declared_size != expected_size or declared_size > max_bytes:
            body.close()
            raise ValueError("OUTPUT_CHECKSUM_SIZE_MISMATCH")
        digest = hashlib.sha256()
        read_size = 0
        try:
            for chunk in body.iter_chunks(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                read_size += len(chunk)
                if read_size > expected_size or read_size > max_bytes:
                    raise ValueError("OUTPUT_CHECKSUM_SIZE_MISMATCH")
                digest.update(chunk)
        finally:
            body.close()
        if read_size != expected_size or digest.hexdigest() != expected_sha256:
            raise ValueError("OUTPUT_CHECKSUM_MISMATCH")

    async def download_object(
        self,
        object_key: str,
        destination: Path,
        *,
        expected_size: int,
        max_bytes: int,
    ) -> DownloadResult:
        return await asyncio.to_thread(
            self._download_object, object_key, destination, expected_size, max_bytes
        )

    def _download_object(
        self, object_key: str, destination: Path, expected_size: int, max_bytes: int
    ) -> DownloadResult:
        response = self.client.get_object(Bucket=self.settings.S3_BUCKET, Key=object_key)
        body = response["Body"]
        size = int(response["ContentLength"])
        if size != expected_size or size > max_bytes:
            body.close()
            raise ValueError("OBJECT_SIZE_MISMATCH")
        digest = hashlib.sha256()
        written = 0
        try:
            with destination.open("xb") as output:
                for chunk in body.iter_chunks(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    written += len(chunk)
                    if written > expected_size or written > max_bytes:
                        raise ValueError("OBJECT_SIZE_MISMATCH")
                    digest.update(chunk)
                    output.write(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        finally:
            body.close()
        if written != expected_size:
            destination.unlink(missing_ok=True)
            raise ValueError("OBJECT_SIZE_MISMATCH")
        return DownloadResult(size_bytes=written, sha256=digest.hexdigest())

    async def delete_object(self, object_key: str) -> None:
        await asyncio.to_thread(
            self.client.delete_object, Bucket=self.settings.S3_BUCKET, Key=object_key
        )

    async def check_bucket_access(self) -> None:
        await asyncio.to_thread(self.client.head_bucket, Bucket=self.settings.S3_BUCKET)
