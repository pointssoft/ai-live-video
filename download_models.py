#!/usr/bin/env python3
"""Download and verify the model artifacts required by MimicMotion.

Run from the repository root on Linux:
    python download_models.py

Optional environment variables:
    HF_TOKEN       Hugging Face access token, if the SVD repository requires it.
    HF_ENDPOINT    Hugging Face endpoint (for example, https://hf-mirror.com).
"""

from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

try:
    from huggingface_hub import snapshot_download
except ImportError as exc:
    raise SystemExit(
        "Missing dependency. Install it with: "
        "python3 -m pip install 'huggingface_hub>=0.28,<1'"
    ) from exc

ROOT = Path(__file__).resolve().parent
MODELS_DIR = ROOT / "models"
SVD_DIR = MODELS_DIR / "SVD" / "stable-video-diffusion-img2vid-xt-1-1"

CORE_ARTIFACTS = (
    (
        "DWPose/yolox_l.onnx",
        "https://huggingface.co/yzd-v/DWPose/resolve/main/yolox_l.onnx?download=true",
        216_746_733,
    ),
    (
        "DWPose/dw-ll_ucoco_384.onnx",
        "https://huggingface.co/yzd-v/DWPose/resolve/main/dw-ll_ucoco_384.onnx?download=true",
        134_399_116,
    ),
    (
        "MimicMotion_1-1.pth",
        "https://huggingface.co/tencent/MimicMotion/resolve/main/MimicMotion_1-1.pth?download=true",
        3_049_867_447,
    ),
)

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


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.2f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def download_with_resume(relative_path: str, url: str, expected_size: int) -> None:
    destination = MODELS_DIR / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)

    current_size = destination.stat().st_size if destination.exists() else 0
    if current_size == expected_size:
        print(f"SKIP {relative_path}: already complete ({format_bytes(current_size)})")
        return
    if current_size > expected_size:
        print(f"RESET {relative_path}: local file is larger than expected")
        destination.unlink()
        current_size = 0

    headers = {"User-Agent": "MimicMotion-artifact-downloader/1.0"}
    if current_size:
        headers["Range"] = f"bytes={current_size}-"
        mode = "ab"
        print(f"RESUME {relative_path} from {format_bytes(current_size)}")
    else:
        mode = "wb"
        print(f"DOWNLOAD {relative_path} ({format_bytes(expected_size)})")

    request = urllib.request.Request(url, headers=headers)
    try:
        response = urllib.request.urlopen(request, timeout=120)
    except Exception:
        if current_size:
            print(f"Resume failed for {relative_path}; retrying from the beginning")
            destination.unlink(missing_ok=True)
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "MimicMotion-artifact-downloader/1.0"},
            )
            response = urllib.request.urlopen(request, timeout=120)
            mode = "wb"
        else:
            raise

    downloaded = current_size if mode == "ab" else 0
    next_report = downloaded + 128 * 1024 * 1024
    with response, destination.open(mode) as output:
        while True:
            chunk = response.read(8 * 1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
            downloaded += len(chunk)
            if downloaded >= next_report:
                print(
                    f"  {relative_path}: {format_bytes(downloaded)} / "
                    f"{format_bytes(expected_size)}"
                )
                next_report = downloaded + 128 * 1024 * 1024

    actual_size = destination.stat().st_size
    if actual_size != expected_size:
        raise RuntimeError(
            f"Invalid size for {relative_path}: expected {expected_size}, got {actual_size}. "
            "Run this script again to resume."
        )
    print(f"OK {relative_path}: {format_bytes(actual_size)}")


def download_svd() -> None:
    print("DOWNLOAD SVD repository")
    snapshot_download(
        repo_id="stabilityai/stable-video-diffusion-img2vid-xt-1-1",
        local_dir=SVD_DIR,
        token=os.environ.get("HF_TOKEN") or None,
        max_workers=2,
    )


def verify_svd() -> None:
    missing = []
    for relative_path in SVD_REQUIRED_FILES:
        path = SVD_DIR / relative_path
        if not path.is_file() or path.stat().st_size == 0:
            missing.append(str(path.relative_to(ROOT)))
    if missing:
        raise RuntimeError("Missing required SVD files:\n  " + "\n  ".join(missing))
    print("OK required SVD files")


def main() -> int:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for relative_path, url, expected_size in CORE_ARTIFACTS:
        download_with_resume(relative_path, url, expected_size)
    download_svd()
    verify_svd()
    total_size = sum(path.stat().st_size for path in MODELS_DIR.rglob("*") if path.is_file())
    print(f"All model downloads completed: {format_bytes(total_size)} in {MODELS_DIR}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        raise SystemExit("Download interrupted. Run the script again to resume.") from None
    except Exception as exc:
        raise SystemExit(f"Download failed: {exc}") from exc
