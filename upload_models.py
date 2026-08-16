#!/usr/bin/env python3
"""Upload and verify local MimicMotion artifacts on a Runpod Network Volume.

Run from the repository root on Linux after download_models.py:
    python upload_models.py

Required environment variables (a root .env file is also supported):
    RUNPOD_S3_ENDPOINT
    RUNPOD_S3_REGION
    RUNPOD_S3_ACCESS_KEY
    RUNPOD_S3_SECRET_KEY
    RUNPOD_NETWORK_VOLUME_ID
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import boto3
    from boto3.s3.transfer import TransferConfig
    from botocore.config import Config
    from botocore.exceptions import ClientError
except ImportError as exc:
    raise SystemExit(
        "Missing dependency. Install it with: python3 -m pip install 'boto3>=1.35,<2'"
    ) from exc

ROOT = Path(__file__).resolve().parent
MODELS_DIR = ROOT / "models"
ENV_FILE = ROOT / ".env"
READY_KEY = "ARTIFACTS_READY"

REQUIRED_ENV = (
    "RUNPOD_S3_ENDPOINT",
    "RUNPOD_S3_REGION",
    "RUNPOD_S3_ACCESS_KEY",
    "RUNPOD_S3_SECRET_KEY",
    "RUNPOD_NETWORK_VOLUME_ID",
)

EXPECTED_CORE_FILES = {
    "models/DWPose/yolox_l.onnx": 216_746_733,
    "models/DWPose/dw-ll_ucoco_384.onnx": 134_399_116,
    "models/MimicMotion_1-1.pth": 3_049_867_447,
}

SVD_PREFIX = "models/SVD/stable-video-diffusion-img2vid-xt-1-1/"
SVD_REQUIRED_FILES = (
    "model_index.json",
    "feature_extractor/preprocessor_config.json",
    "image_encoder/config.json",
    "image_encoder/model.fp16.safetensors",
    "scheduler/scheduler_config.json",
    "unet/config.json",
    "vae/config.json",
    "vae/diffusion_pytorch_model.fp16.safetensors",
)


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if name:
            os.environ.setdefault(name, value)


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.2f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def validate_environment() -> None:
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing environment variables: " + ", ".join(missing))


def local_files() -> list[Path]:
    if not MODELS_DIR.is_dir():
        raise RuntimeError(f"Models directory does not exist: {MODELS_DIR}")

    for key, expected_size in EXPECTED_CORE_FILES.items():
        path = ROOT / key
        actual_size = path.stat().st_size if path.is_file() else None
        if actual_size != expected_size:
            raise RuntimeError(
                f"Invalid local artifact {key}: expected {expected_size}, got {actual_size}"
            )

    for relative_path in SVD_REQUIRED_FILES:
        path = ROOT / SVD_PREFIX / relative_path
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Missing local SVD artifact: {path.relative_to(ROOT)}")

    files = sorted(path for path in MODELS_DIR.rglob("*") if path.is_file())
    if not files:
        raise RuntimeError("No files found under models/")
    return files


def create_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["RUNPOD_S3_ENDPOINT"],
        region_name=os.environ["RUNPOD_S3_REGION"],
        aws_access_key_id=os.environ["RUNPOD_S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["RUNPOD_S3_SECRET_KEY"],
        config=Config(
            connect_timeout=30,
            read_timeout=300,
            retries={"max_attempts": 10, "mode": "adaptive"},
        ),
    )


def remote_size(client, bucket: str, key: str) -> int | None:
    try:
        return int(client.head_object(Bucket=bucket, Key=key)["ContentLength"])
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise


def verify_remote(client, bucket: str, expected: dict[str, int]) -> None:
    failures = []
    for key, expected_size in expected.items():
        actual_size = remote_size(client, bucket, key)
        if actual_size != expected_size:
            failures.append(f"{key}: expected {expected_size}, got {actual_size}")
        else:
            print(f"VERIFY {key}: {format_bytes(actual_size)}")
    if failures:
        raise RuntimeError("Remote verification failed:\n  " + "\n  ".join(failures))


def main() -> int:
    load_dotenv(ENV_FILE)
    validate_environment()
    files = local_files()
    client = create_client()
    bucket = os.environ["RUNPOD_NETWORK_VOLUME_ID"]
    transfer_config = TransferConfig(
        multipart_threshold=64 * 1024 * 1024,
        multipart_chunksize=64 * 1024 * 1024,
        max_concurrency=2,
        use_threads=True,
    )

    expected: dict[str, int] = {}
    for index, path in enumerate(files, start=1):
        key = f"models/{path.relative_to(MODELS_DIR).as_posix()}"
        size = path.stat().st_size
        expected[key] = size
        existing_size = remote_size(client, bucket, key)
        if existing_size == size:
            print(f"[{index}/{len(files)}] SKIP {key}: {format_bytes(size)}")
            continue

        print(f"[{index}/{len(files)}] UPLOAD {key}: {format_bytes(size)}")
        client.upload_file(str(path), bucket, key, Config=transfer_config)
        uploaded_size = remote_size(client, bucket, key)
        if uploaded_size != size:
            raise RuntimeError(
                f"Upload size mismatch for {key}: local={size}, remote={uploaded_size}"
            )

    verify_remote(client, bucket, expected)
    client.put_object(Bucket=bucket, Key=READY_KEY, Body=b"")
    if remote_size(client, bucket, READY_KEY) != 0:
        raise RuntimeError(f"Could not verify completion marker {READY_KEY}")

    total_size = sum(expected.values())
    print(
        f"Upload completed: {len(expected)} files, {format_bytes(total_size)}. "
        f"Created {READY_KEY}."
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        raise SystemExit("Upload interrupted. Run the script again to resume.") from None
    except Exception as exc:
        raise SystemExit(f"Upload failed: {exc}") from exc
