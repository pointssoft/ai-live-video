import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GenerationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portrait_id: uuid.UUID
    motion_asset_id: uuid.UUID


class GenerationExecutionResponse(BaseModel):
    state: str
    attempt_id: uuid.UUID | None
    provider_status: str | None
    progress_stage: str | None
    failure_code: str | None
    failure_message: str | None


class GenerationOutputResponse(BaseModel):
    content_type: str
    size_bytes: int
    sha256: str
    download_url: str
    download_url_expires_at: datetime


class GenerationResponse(BaseModel):
    id: uuid.UUID
    portrait_id: uuid.UUID
    motion_asset_id: uuid.UUID
    status: str
    execution: GenerationExecutionResponse
    output: GenerationOutputResponse | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    timed_out_at: datetime | None
    canceled_at: datetime | None


class GenerationPage(BaseModel):
    items: list[GenerationResponse]
    next_cursor: str | None
