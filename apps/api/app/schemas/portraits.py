import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PortraitCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_asset_id: uuid.UUID


class PortraitAssetResponse(BaseModel):
    id: uuid.UUID
    content_type: str
    size_bytes: int
    sha256: str
    width: int
    height: int


class PortraitResponse(BaseModel):
    id: uuid.UUID
    status: str
    original_asset: PortraitAssetResponse
    image_url: str
    image_url_expires_at: datetime
    thumbnail_url: str | None = None
    thumbnail_url_expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PortraitPage(BaseModel):
    items: list[PortraitResponse]
    next_cursor: str | None


class PortraitListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = None
