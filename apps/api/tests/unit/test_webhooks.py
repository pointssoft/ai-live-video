import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.main import app
from app.schemas.webhooks import RunpodWebhookPayload
from app.services.runpod import RunpodClient


def test_webhook_accepts_runpod_job_id_alias() -> None:
    payload = RunpodWebhookPayload.model_validate(
        {"job_id": "job-123", "status": "IN_PROGRESS", "progress": "RUNNING_INFERENCE"}
    )
    assert payload.runpod_job_id == "job-123"


def test_webhook_accepts_provider_id_and_event_id() -> None:
    payload = RunpodWebhookPayload.model_validate(
        {"id": "job-456", "event_id": "event-1", "status": "COMPLETED"}
    )
    assert payload.runpod_job_id == "job-456"
    assert payload.event_id == "event-1"


def test_webhook_requires_job_id() -> None:
    with pytest.raises(ValidationError):
        RunpodWebhookPayload.model_validate({"status": "FAILED"})


def test_webhook_rejects_conflicting_job_ids() -> None:
    with pytest.raises(ValidationError):
        RunpodWebhookPayload.model_validate(
            {"id": "job-1", "job_id": "job-2", "status": "IN_PROGRESS"}
        )


async def test_runpod_submission_includes_configured_webhook() -> None:
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
        AUTH_TOKEN_PEPPER="x" * 32,
        S3_ENDPOINT_URL="https://storage.example",
        S3_BUCKET="bucket",
        S3_ACCESS_KEY_ID="key",
        S3_SECRET_ACCESS_KEY="secret",
        RUNPOD_API_KEY="runpod-key",
        RUNPOD_ENDPOINT_ID="endpoint",
        RUNPOD_WEBHOOK_URL="https://api.example.com/api/v1/webhooks/runpod",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/endpoint/run"
        assert json.loads(request.read()) == {
            "input": {},
            "webhook": "https://api.example.com/api/v1/webhooks/runpod",
        }
        return httpx.Response(200, json={"id": "job-1", "status": "IN_QUEUE"})

    client = RunpodClient(settings)
    await client.client.aclose()
    client.client = httpx.AsyncClient(
        base_url="https://api.runpod.ai/v2",
        transport=httpx.MockTransport(handler),
    )
    try:
        result = await client.submit({})
    finally:
        await client.close()
    assert result.job_id == "job-1"


def test_webhook_rejects_missing_token_before_processing() -> None:
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
        AUTH_TOKEN_PEPPER="x" * 32,
        S3_ENDPOINT_URL="https://storage.example",
        S3_BUCKET="bucket",
        S3_ACCESS_KEY_ID="key",
        S3_SECRET_ACCESS_KEY="secret",
        RUNPOD_WEBHOOK_TOKEN="w" * 32,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/webhooks/runpod",
                json={"id": "job-1", "status": "IN_PROGRESS"},
            )
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "WEBHOOK_UNAUTHORIZED"


def test_webhook_rejects_invalid_payload_with_valid_token() -> None:
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
        AUTH_TOKEN_PEPPER="x" * 32,
        S3_ENDPOINT_URL="https://storage.example",
        S3_BUCKET="bucket",
        S3_ACCESS_KEY_ID="key",
        S3_SECRET_ACCESS_KEY="secret",
        RUNPOD_WEBHOOK_TOKEN="w" * 32,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/webhooks/runpod?token=" + "w" * 32,
                json={"status": "FAILED"},
            )
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "WEBHOOK_PAYLOAD_INVALID"


