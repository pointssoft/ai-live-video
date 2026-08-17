from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RunpodWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: str | None = Field(default=None, max_length=255)
    id: str | None = Field(default=None, max_length=255)
    job_id: str | None = Field(default=None, max_length=255)
    status: str = Field(min_length=1, max_length=32)
    progress: str | None = Field(default=None, max_length=64)
    output: Any = None
    error: Any = None

    @model_validator(mode="after")
    def require_job_id(self) -> "RunpodWebhookPayload":
        if not self.id and not self.job_id:
            raise ValueError("RUNPOD_WEBHOOK_JOB_ID_MISSING")
        if self.id and self.job_id and self.id != self.job_id:
            raise ValueError("RUNPOD_WEBHOOK_JOB_ID_MISMATCH")
        return self

    @property
    def runpod_job_id(self) -> str:
        return self.job_id or self.id or ""
