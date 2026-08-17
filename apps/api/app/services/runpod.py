from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import Settings


@dataclass(frozen=True)
class RunpodSubmitResult:
    job_id: str
    status: str


@dataclass(frozen=True)
class RunpodStatusResult:
    job_id: str
    status: str
    output: Any = None
    error: Any = None
    progress: str | None = None


class RunpodService(Protocol):
    async def submit(self, worker_input: dict[str, object]) -> RunpodSubmitResult: ...

    async def status(self, job_id: str) -> RunpodStatusResult: ...

    async def cancel(self, job_id: str) -> None: ...


class RunpodClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.RUNPOD_API_KEY or not settings.RUNPOD_ENDPOINT_ID:
            raise RuntimeError("Runpod orchestration is not configured")
        self.endpoint_id = settings.RUNPOD_ENDPOINT_ID
        self.webhook_url = settings.RUNPOD_WEBHOOK_URL
        self.client = httpx.AsyncClient(
            base_url=settings.RUNPOD_API_BASE_URL.rstrip("/"),
            headers={"Authorization": f"Bearer {settings.RUNPOD_API_KEY}"},
            timeout=settings.RUNPOD_REQUEST_TIMEOUT_SECONDS,
        )

    async def submit(self, worker_input: dict[str, object]) -> RunpodSubmitResult:
        request_payload: dict[str, object] = {"input": worker_input}
        if self.webhook_url:
            request_payload["webhook"] = self.webhook_url
        response = await self.client.post(
            f"/{self.endpoint_id}/run", json=request_payload
        )
        response.raise_for_status()
        payload = response.json()
        job_id = payload.get("id")
        status = payload.get("status", "IN_QUEUE")
        if not isinstance(job_id, str) or not job_id:
            raise ValueError("Runpod submission did not return a job ID")
        if not isinstance(status, str):
            raise ValueError("Runpod submission returned an invalid status")
        return RunpodSubmitResult(job_id=job_id, status=status)

    async def status(self, job_id: str) -> RunpodStatusResult:
        response = await self.client.get(f"/{self.endpoint_id}/status/{job_id}")
        response.raise_for_status()
        payload = response.json()
        status = payload.get("status")
        if not isinstance(status, str):
            raise ValueError("Runpod status response is invalid")
        progress = payload.get("progress")
        if not isinstance(progress, str):
            progress = None
        return RunpodStatusResult(
            job_id=job_id,
            status=status,
            output=payload.get("output"),
            error=payload.get("error"),
            progress=progress,
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def cancel(self, job_id: str) -> None:
        response = await self.client.post(f"/{self.endpoint_id}/cancel/{job_id}")
        response.raise_for_status()
