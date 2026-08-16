import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UploadKind(enum.StrEnum):
    PORTRAIT_ORIGINAL = "PORTRAIT_ORIGINAL"
    MOTION_INPUT = "MOTION_INPUT"


class UploadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: UploadKind
    content_type: str
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class UploadSessionResponse(BaseModel):
    upload_id: uuid.UUID
    state: str
    object_key: str
    method: str = "PUT"
    upload_url: str
    expires_at: datetime
    required_headers: dict[str, str]


class ValidationErrorResponse(BaseModel):
    code: str
    message: str


class UploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    state: str
    content_type: str
    detected_content_type: str | None
    size_bytes: int
    sha256: str
    width: int | None
    height: int | None
    duration_ms: int | None
    fps: float | None
    frame_count: int | None
    video_codec: str | None
    created_at: datetime
    uploaded_at: datetime | None
    validated_at: datetime | None
    ready_at: datetime | None
    validation_error_code: str | None
    validation_error_detail: str | None
