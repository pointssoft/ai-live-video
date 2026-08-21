from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

SHA = r"^[0-9a-f]{64}$"

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class InputObject(StrictModel):
    object_key: str
    download_url: str
    expires_at: datetime
    content_type: str
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=SHA)

class MotionObject(InputObject):
    min_duration_ms: int = 5000
    max_duration_ms: int = 15000

class OutputObject(StrictModel):
    object_key: str
    upload_url: str
    head_url: str
    expires_at: datetime
    content_type: Literal["video/mp4"] = "video/mp4"
    max_bytes: int = Field(gt=0)
    required_headers: dict[str, str]

class InferenceProfile(StrictModel):
    profile: Literal[
        "mimicmotion-v1.1-balanced-v1", "mimicmotion-v1.1-quality-v1"
    ]
    profile_revision: Literal[1]
    model_version: Literal["v1.1"]
    resolution: Literal[576]
    tile_size: Literal[72]
    tile_overlap: Literal[6, 12]
    num_inference_steps: Literal[25, 35]
    noise_aug_strength: Literal[0.0, 0.02]
    guidance_scale: Literal[2.0, 2.5]
    sample_stride: Literal[1, 2]
    output_fps: Literal[15]
    seed: int = Field(ge=0, le=9_007_199_254_740_991)

    @model_validator(mode="after")
    def validate_profile_snapshot(self):
        expected = {
            "mimicmotion-v1.1-balanced-v1": (6, 25, 0.0, 2.0, 2),
            "mimicmotion-v1.1-quality-v1": (12, 35, 0.02, 2.5, 1),
        }[self.profile]
        actual = (
            self.tile_overlap,
            self.num_inference_steps,
            self.noise_aug_strength,
            self.guidance_scale,
            self.sample_stride,
        )
        if actual != expected:
            raise ValueError("inference parameters do not match the selected profile")
        return self

class WorkerInputV1(StrictModel):
    schema_version: Literal["1.0"]
    generation_id: UUID
    attempt_id: UUID
    portrait: InputObject
    motion_video: MotionObject
    output: OutputObject
    inference: InferenceProfile

    @model_validator(mode="after")
    def validate_keys(self):
        for key in (self.portrait.object_key, self.motion_video.object_key, self.output.object_key):
            if "\\" in key or key.startswith("/") or any(p in {"", ".", ".."} for p in key.split("/")):
                raise ValueError("invalid object key")
        if not self.output.object_key.endswith("/output.mp4"):
            raise ValueError("output key must end with /output.mp4")
        if (
            self.portrait.expires_at <= datetime.now(timezone.utc)
            or self.motion_video.expires_at <= datetime.now(timezone.utc)
            or self.output.expires_at <= datetime.now(timezone.utc)
        ):
            raise ValueError("signed URL expired")
        return self
