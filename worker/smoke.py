import json
import os
import platform
import subprocess
import time
import traceback
from pathlib import Path
from typing import Any


def _bootstrap_from_s3(root: Path) -> tuple[Path, Path]:
    required = (
        "BOOTSTRAP_S3_ENDPOINT",
        "BOOTSTRAP_S3_REGION",
        "BOOTSTRAP_S3_ACCESS_KEY",
        "BOOTSTRAP_S3_SECRET_KEY",
        "BOOTSTRAP_S3_BUCKET",
    )
    if not all(os.getenv(name) for name in required):
        return (
            Path(os.getenv("MODEL_ROOT", "/runpod-volume/models")),
            Path(os.getenv("ARTIFACTS_READY_PATH", "/runpod-volume/ARTIFACTS_READY")),
        )

    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        endpoint_url=os.environ["BOOTSTRAP_S3_ENDPOINT"],
        region_name=os.environ["BOOTSTRAP_S3_REGION"],
        aws_access_key_id=os.environ["BOOTSTRAP_S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["BOOTSTRAP_S3_SECRET_KEY"],
        config=Config(
            connect_timeout=30,
            read_timeout=300,
            retries={"max_attempts": 10, "mode": "adaptive"},
        ),
    )
    bucket = os.environ["BOOTSTRAP_S3_BUCKET"]
    models = root / "models"
    models.mkdir(parents=True, exist_ok=True)
    continuation = None
    count = 0
    while True:
        request: dict[str, Any] = {"Bucket": bucket, "Prefix": "models/", "MaxKeys": 1000}
        if continuation:
            request["ContinuationToken"] = continuation
        response = client.list_objects_v2(**request)
        for item in response.get("Contents", []):
            key = item["Key"]
            destination = root / key
            destination.parent.mkdir(parents=True, exist_ok=True)
            print(f"Downloading {key} ({item['Size']} bytes)", flush=True)
            client.download_file(bucket, key, str(destination))
            count += 1
        if not response.get("IsTruncated"):
            break
        continuation = response["NextContinuationToken"]
    if count == 0:
        raise RuntimeError("No model artifacts were found in bootstrap storage")
    marker = root / "ARTIFACTS_READY"
    marker.touch()
    return models, marker


def _publish_result(result: dict[str, Any]) -> None:
    if not os.getenv("BOOTSTRAP_S3_BUCKET") or not os.getenv("SMOKE_RESULT_KEY"):
        return
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=os.environ["BOOTSTRAP_S3_ENDPOINT"],
        region_name=os.environ["BOOTSTRAP_S3_REGION"],
        aws_access_key_id=os.environ["BOOTSTRAP_S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["BOOTSTRAP_S3_SECRET_KEY"],
    )
    client.put_object(
        Bucket=os.environ["BOOTSTRAP_S3_BUCKET"],
        Key=os.environ["SMOKE_RESULT_KEY"],
        Body=json.dumps(result, sort_keys=True).encode(),
        ContentType="application/json",
    )


def run_model_smoke() -> None:
    result: dict[str, Any] = {
        "status": "failed",
        "python": platform.python_version(),
    }
    try:
        import torch

        result["torch"] = torch.__version__
        result["cuda_available"] = torch.cuda.is_available()
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable")
        result["cuda_device"] = torch.cuda.get_device_name(0)
        result["cuda_memory_total"] = torch.cuda.get_device_properties(0).total_memory

        root = Path(os.getenv("SMOKE_ARTIFACT_ROOT", "/tmp/mimicmotion-smoke-artifacts"))
        model_root, marker = _bootstrap_from_s3(root)
        from worker.services.model_service import ModelService

        service = ModelService(model_root, marker)
        service._validate_artifacts()
        result["artifacts_valid"] = True
        service._load()
        result["pipeline_loaded"] = True
        result["unet_dtype"] = str(next(service._pipeline.unet.parameters()).dtype)
        result["pose_dtype"] = str(next(service._pipeline.pose_net.parameters()).dtype)

        if os.getenv("SMOKE_CUDA_TRANSFER", "true").lower() == "true":
            service._pipeline.unet.to("cuda")
            service._pipeline.pose_net.to("cuda")
            result["cuda_transfer"] = True
            result["cuda_memory_allocated"] = torch.cuda.memory_allocated()
            result["cuda_memory_reserved"] = torch.cuda.memory_reserved()

        result["status"] = "succeeded"
    except Exception as exc:  # noqa: BLE001 - smoke must publish every fatal failure
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)[:1000]
        result["traceback"] = traceback.format_exc(limit=8)[-4000:]
    finally:
        _publish_result(result)
        print(json.dumps(result, sort_keys=True), flush=True)
    if result["status"] != "succeeded":
        raise SystemExit(1)


def run_inference_smoke() -> None:
    result: dict[str, Any] = {
        "status": "failed",
        "python": platform.python_version(),
        "clips": [],
    }
    try:
        import boto3
        import torch

        from worker.contracts import InferenceProfile
        from worker.services.model_service import ModelService

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable")
        result["cuda_device"] = torch.cuda.get_device_name(0)
        result["cuda_memory_total"] = torch.cuda.get_device_properties(0).total_memory

        root = Path(os.getenv("SMOKE_ARTIFACT_ROOT", "/tmp/mimicmotion-smoke-artifacts"))
        model_root, marker = _bootstrap_from_s3(root)
        service = ModelService(model_root, marker)
        service._validate_artifacts()

        client = boto3.client(
            "s3",
            endpoint_url=os.environ["BOOTSTRAP_S3_ENDPOINT"],
            region_name=os.environ["BOOTSTRAP_S3_REGION"],
            aws_access_key_id=os.environ["BOOTSTRAP_S3_ACCESS_KEY"],
            aws_secret_access_key=os.environ["BOOTSTRAP_S3_SECRET_KEY"],
        )
        bucket = os.environ["BOOTSTRAP_S3_BUCKET"]
        portrait = root / "input.jpg"
        source_motion = root / "source.mp4"
        for key, destination in (
            (os.environ["SMOKE_PORTRAIT_KEY"], portrait),
            (os.environ["SMOKE_MOTION_KEY"], source_motion),
        ):
            response = client.get_object(Bucket=bucket, Key=key)
            body = response["Body"]
            try:
                with destination.open("wb") as output_file:
                    for chunk in body.iter_chunks(chunk_size=1024 * 1024):
                        if chunk:
                            output_file.write(chunk)
            finally:
                body.close()

        profile = InferenceProfile(
            profile="mimicmotion-v1.1-balanced-v1",
            profile_revision=1,
            model_version="v1.1",
            resolution=576,
            tile_size=72,
            tile_overlap=6,
            num_inference_steps=25,
            noise_aug_strength=0.0,
            guidance_scale=2.0,
            sample_stride=2,
            output_fps=15,
            seed=42,
        )
        durations = [int(value) for value in os.getenv("SMOKE_DURATIONS", "5,10,15").split(",")]
        output_prefix = os.getenv("SMOKE_OUTPUT_PREFIX", "smoke/inference")
        for duration in durations:
            motion = root / f"motion-{duration}s.mp4"
            output = root / f"output-{duration}s.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(source_motion),
                    "-t",
                    str(duration),
                    "-an",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    str(motion),
                ],
                check=True,
                capture_output=True,
            )
            torch.cuda.reset_peak_memory_stats()
            started = time.monotonic()
            service.generate(portrait, motion, output, profile)
            elapsed = time.monotonic() - started
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration,size:stream=codec_name,width,height,avg_frame_rate",
                    "-of",
                    "json",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            output_key = f"{output_prefix}/output-{duration}s.mp4"
            client.upload_file(
                str(output),
                bucket,
                output_key,
                ExtraArgs={"ContentType": "video/mp4"},
            )
            clip = {
                "input_duration_seconds": duration,
                "elapsed_seconds": round(elapsed, 3),
                "peak_cuda_bytes": torch.cuda.max_memory_allocated(),
                "output_key": output_key,
                "output_bytes": output.stat().st_size,
                "probe": json.loads(probe.stdout),
            }
            result["clips"].append(clip)
            _publish_result(result)

        result["status"] = "succeeded"
    except Exception as exc:  # noqa: BLE001 - smoke must publish every fatal failure
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)[:1000]
        result["traceback"] = traceback.format_exc(limit=8)[-4000:]
    finally:
        _publish_result(result)
        print(json.dumps(result, sort_keys=True), flush=True)
    if result["status"] != "succeeded":
        raise SystemExit(1)
