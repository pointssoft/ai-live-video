import hashlib
import hmac
from pathlib import Path

import httpx

from worker.errors import WorkerError


class StorageService:
    def __init__(self) -> None:
        self.client = httpx.Client(follow_redirects=False, trust_env=False, timeout=30)

    def download(self, url: str, destination: Path, expected_size: int, expected_sha256: str) -> None:
        written = 0
        digest = hashlib.sha256()
        try:
            with self.client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise WorkerError("INPUT_DOWNLOAD_FAILED", "DOWNLOADING", response.status_code >= 500, "Input download failed.")
                length = response.headers.get("content-length")
                if length and int(length) != expected_size:
                    raise WorkerError("INPUT_SIZE_MISMATCH", "DOWNLOADING", False, "Input size did not match.")
                with destination.open("xb") as output:
                    for chunk in response.iter_bytes(1024 * 1024):
                        written += len(chunk)
                        if written > expected_size:
                            raise WorkerError("INPUT_SIZE_MISMATCH", "DOWNLOADING", False, "Input size did not match.")
                        digest.update(chunk); output.write(chunk)
            if written != expected_size:
                raise WorkerError("INPUT_SIZE_MISMATCH", "DOWNLOADING", False, "Input size did not match.")
            if not hmac.compare_digest(digest.hexdigest(), expected_sha256):
                raise WorkerError("INPUT_CHECKSUM_MISMATCH", "DOWNLOADING", False, "Input checksum did not match.")
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    def upload(self, url: str, source: Path, headers: dict[str, str], max_bytes: int) -> tuple[int, str]:
        size = source.stat().st_size
        if size <= 0 or size > max_bytes:
            raise WorkerError("OUTPUT_TOO_LARGE", "UPLOADING_OUTPUT", False, "Output size is invalid.")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        with source.open("rb") as body:
            response = self.client.put(url, content=body, headers={**headers, "content-length": str(size)})
        if not 200 <= response.status_code < 300:
            raise WorkerError("OUTPUT_UPLOAD_FAILED", "UPLOADING_OUTPUT", response.status_code >= 500, "Output upload failed.")
        return size, digest

    def verify_upload(self, url: str, expected_size: int) -> None:
        response = self.client.head(url)
        if response.status_code != 200:
            raise WorkerError(
                "OUTPUT_VERIFICATION_FAILED",
                "VERIFYING_OUTPUT",
                response.status_code >= 500,
                "Output verification failed.",
            )
        length = response.headers.get("content-length")
        if length is None or int(length) != expected_size:
            raise WorkerError(
                "OUTPUT_SIZE_MISMATCH",
                "VERIFYING_OUTPUT",
                False,
                "Output size did not match.",
            )
