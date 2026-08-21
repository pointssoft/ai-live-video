import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings
from app.models import Generation, GenerationAttempt, MediaAsset
from app.services.storage import StorageService


def default_inference_parameters() -> dict[str, object]:
    return {
        "profile": "mimicmotion-v1.1-balanced-v1",
        "profile_revision": 1,
        "model_version": "v1.1",
        "resolution": 576,
        "tile_size": 72,
        "tile_overlap": 6,
        "num_inference_steps": 25,
        "noise_aug_strength": 0.0,
        "guidance_scale": 2.0,
        "sample_stride": 2,
        "output_fps": 15,
        "seed": 42,
    }


def inference_parameters(profile: str, seed: int) -> dict[str, object]:
    profiles: dict[str, dict[str, object]] = {
        "mimicmotion-v1.1-balanced-v1": default_inference_parameters(),
        "mimicmotion-v1.1-quality-v1": {
            "profile": "mimicmotion-v1.1-quality-v1",
            "profile_revision": 1,
            "model_version": "v1.1",
            "resolution": 576,
            "tile_size": 72,
            "tile_overlap": 12,
            "num_inference_steps": 35,
            "noise_aug_strength": 0.02,
            "guidance_scale": 2.5,
            "sample_stride": 1,
            "output_fps": 15,
            "seed": 42,
        },
    }
    parameters = dict(profiles[profile])
    parameters["seed"] = seed
    return parameters


class WorkerOutputManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_key: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_type: str
    size_bytes: int = Field(gt=0)


class WorkerTimings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_worker_ms: int = Field(ge=0)
    input_validation_ms: int = Field(ge=0)
    input_download_ms: int = Field(ge=0)
    media_processing_ms: int = Field(ge=0)
    model_cache_hit: bool
    model_load_ms: int = Field(ge=0)
    preprocessing_ms: int = Field(ge=0)
    pipeline_ms: int = Field(ge=0)
    output_encoding_ms: int = Field(ge=0)
    output_upload_ms: int = Field(ge=0)
    output_verification_ms: int = Field(ge=0)


class WorkerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    generation_id: uuid.UUID
    attempt_id: uuid.UUID
    status: str
    timings: WorkerTimings | None = None
    output: WorkerOutputManifest


async def build_worker_input(
    settings: Settings,
    storage: StorageService,
    generation: Generation,
    attempt: GenerationAttempt,
    portrait_asset: MediaAsset,
    motion: MediaAsset,
) -> dict[str, object]:
    if portrait_asset.detected_content_type is None or motion.detected_content_type is None:
        raise ValueError("INPUT_METADATA_MISSING")
    ttl = settings.GENERATION_SIGNED_URL_TTL_SECONDS
    portrait_url = await storage.create_download_url(
        portrait_asset.object_key, expires_in_seconds=ttl
    )
    motion_url = await storage.create_download_url(motion.object_key, expires_in_seconds=ttl)
    metadata = {"generation-id": str(generation.id), "attempt-id": str(attempt.id)}
    upload_url = await storage.create_output_upload_url(
        attempt.output_object_key,
        content_type="video/mp4",
        metadata=metadata,
        expires_in_seconds=ttl,
    )
    head_url = await storage.create_head_url(
        attempt.output_object_key, expires_in_seconds=ttl
    )
    output_expires = min(upload_url.expires_at, head_url.expires_at)
    inference = attempt.parameters_json
    return {
        "schema_version": "1.0",
        "generation_id": str(generation.id),
        "attempt_id": str(attempt.id),
        "portrait": {
            "object_key": portrait_asset.object_key,
            "download_url": portrait_url.url,
            "expires_at": portrait_url.expires_at.isoformat(),
            "content_type": portrait_asset.detected_content_type,
            "size_bytes": portrait_asset.size_bytes,
            "sha256": portrait_asset.sha256,
        },
        "motion_video": {
            "object_key": motion.object_key,
            "download_url": motion_url.url,
            "expires_at": motion_url.expires_at.isoformat(),
            "content_type": motion.detected_content_type,
            "size_bytes": motion.size_bytes,
            "sha256": motion.sha256,
            "min_duration_ms": settings.MOTION_MIN_DURATION_MS,
            "max_duration_ms": settings.MOTION_MAX_DURATION_MS,
        },
        "output": {
            "object_key": attempt.output_object_key,
            "upload_url": upload_url.url,
            "head_url": head_url.url,
            "expires_at": output_expires.isoformat(),
            "content_type": "video/mp4",
            "max_bytes": settings.MAX_GENERATED_OUTPUT_BYTES,
            "required_headers": upload_url.headers,
        },
        "inference": inference,
    }
