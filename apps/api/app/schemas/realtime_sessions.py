import uuid

from pydantic import BaseModel


class RealtimeSessionCreate(BaseModel):
    portrait_id: uuid.UUID


class RealtimeSessionResponse(BaseModel):
    session_id: uuid.UUID
    room_name: str
    server_url: str
    participant_token: str
    viewer_token: str
    expires_in_seconds: int
    pod_id: str | None = None
