import json
import uuid
from typing import Any

import httpx
import pytest
from livekit import api

from app.api.v1 import realtime_sessions
from app.api.v1.realtime_sessions import (
    create_agent_name,
    create_participant_token,
    create_runpod_pod,
    create_viewer_token,
    dispatch_agent,
)
from app.core.config import Settings
from app.core.errors import ApiError


def realtime_settings(
    image: str = "registry.example/realtime-worker:sha-0123456789ab",
) -> Settings:
    return Settings(
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
        AUTH_TOKEN_PEPPER="x" * 32,
        S3_ENDPOINT_URL="https://storage.example",
        S3_BUCKET="bucket",
        S3_ACCESS_KEY_ID="key",
        S3_SECRET_ACCESS_KEY="secret",
        RUNPOD_API_KEY="runpod-key",
        RUNPOD_REALTIME_IMAGE=image,
        LIVEKIT_URL="wss://livekit.example",
        LIVEKIT_API_KEY="livekit-key",
        LIVEKIT_API_SECRET="s" * 32,
    )


def test_realtime_token_is_scoped_to_room() -> None:
    token = create_participant_token(
        api_key="test-key",
        api_secret="s" * 32,
        room_name="realtime-test",
        identity="user-test",
        metadata=json.dumps({"portrait_id": "portrait-test"}),
        ttl_seconds=300,
    )

    claims = api.TokenVerifier("test-key", "s" * 32).verify(token)

    assert claims.identity == "user-test"
    assert claims.video is not None
    assert claims.video.room_join is True
    assert claims.video.room == "realtime-test"
    assert claims.video.can_publish is True
    assert claims.video.can_subscribe is True
    assert claims.video.can_publish_data is True
    assert json.loads(claims.metadata)["portrait_id"] == "portrait-test"


def test_realtime_viewer_token_is_read_only() -> None:
    token = create_viewer_token(
        api_key="test-key",
        api_secret="s" * 32,
        room_name="realtime-test",
        identity="viewer-test",
        ttl_seconds=300,
    )

    claims = api.TokenVerifier("test-key", "s" * 32).verify(token)

    assert claims.identity == "viewer-test"
    assert claims.video is not None
    assert claims.video.room_join is True
    assert claims.video.room == "realtime-test"
    assert claims.video.can_publish is False
    assert claims.video.can_subscribe is True
    assert claims.video.can_publish_data is False


def test_realtime_agent_name_is_unique_to_session() -> None:
    first_session = uuid.uuid4()
    second_session = uuid.uuid4()

    assert create_agent_name(first_session) == f"liveportrait-{first_session}"
    assert create_agent_name(first_session) != create_agent_name(second_session)


async def test_runpod_worker_uses_session_agent_name(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = realtime_settings()
    request: dict[str, Any] = {}

    class FakeResponse:
        status_code = 201

        def json(self) -> dict[str, str]:
            return {"id": "pod-test"}

    class FakeAsyncClient:
        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, **kwargs: Any) -> FakeResponse:
            request["url"] = url
            request["payload"] = kwargs["json"]
            return FakeResponse()

    monkeypatch.setattr(realtime_sessions.httpx, "AsyncClient", FakeAsyncClient)

    pod_id = await create_runpod_pod(settings, uuid.uuid4(), "liveportrait-session-test")

    assert pod_id == "pod-test"
    assert request["url"] == "https://rest.runpod.io/v1/pods"
    assert request["payload"]["imageName"] == "registry.example/realtime-worker:sha-0123456789ab"
    assert request["payload"]["env"]["LIVEKIT_AGENT_NAME"] == "liveportrait-session-test"


async def test_runpod_worker_rejects_nonimmutable_image() -> None:
    with pytest.raises(ApiError) as caught:
        await create_runpod_pod(
            realtime_settings("registry.example/realtime-worker:latest"),
            uuid.uuid4(),
            "liveportrait-session-test",
        )

    assert caught.value.status_code == 503
    assert caught.value.code == "RUNPOD_IMAGE_INVALID"


async def test_runpod_capacity_error_is_actionable(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        status_code = 400

        def json(self) -> dict[str, str]:
            return {"error": "There are no GPU instances available in secure cloud."}

    class FakeAsyncClient:
        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, **kwargs: Any) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(realtime_sessions.httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(ApiError) as caught:
        await create_runpod_pod(
            realtime_settings(),
            uuid.uuid4(),
            "liveportrait-session-test",
        )

    assert caught.value.status_code == 503
    assert caught.value.code == "RUNPOD_CAPACITY_UNAVAILABLE"
    assert caught.value.details == {"provider_status": 400}


async def test_runpod_timeout_is_actionable(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeAsyncClient:
        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, **kwargs: Any) -> None:
            raise httpx.ReadTimeout("provider timed out")

    monkeypatch.setattr(realtime_sessions.httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(ApiError) as caught:
        await create_runpod_pod(
            realtime_settings(),
            uuid.uuid4(),
            "liveportrait-session-test",
        )

    assert caught.value.status_code == 503
    assert caught.value.code == "RUNPOD_TIMEOUT"


async def test_dispatch_retries_until_worker_registers(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeAgentDispatchService:
        def __init__(self) -> None:
            self.create_attempts = 0

        async def list_dispatch(self, room_name: str) -> list[Any]:
            assert room_name == "realtime-test"
            return []

        async def create_dispatch(self, request: Any) -> None:
            self.create_attempts += 1
            assert request.agent_name == "liveportrait-test"
            assert request.room == "realtime-test"
            if self.create_attempts < 3:
                raise RuntimeError("agent is not available")

    class FakeLiveKitAPI:
        def __init__(self) -> None:
            self.agent_dispatch = FakeAgentDispatchService()
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    client = FakeLiveKitAPI()
    sleep_delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_delays.append(delay)

    monkeypatch.setattr(realtime_sessions.api, "LiveKitAPI", lambda **kwargs: client)
    monkeypatch.setattr(realtime_sessions.asyncio, "sleep", fake_sleep)

    dispatched = await dispatch_agent(
        server_url="wss://livekit.example",
        api_key="key",
        api_secret="secret",
        room_name="realtime-test",
        agent_name="liveportrait-test",
        max_attempts=3,
        retry_delay_seconds=0.25,
    )

    assert dispatched is True
    assert client.agent_dispatch.create_attempts == 3
    assert sleep_delays == [0.25, 0.25]
    assert client.closed is True


async def test_dispatch_stops_after_bounded_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeAgentDispatchService:
        def __init__(self) -> None:
            self.create_attempts = 0

        async def list_dispatch(self, room_name: str) -> list[Any]:
            return []

        async def create_dispatch(self, request: Any) -> None:
            self.create_attempts += 1
            raise RuntimeError("agent is not available")

    class FakeLiveKitAPI:
        def __init__(self) -> None:
            self.agent_dispatch = FakeAgentDispatchService()
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    client = FakeLiveKitAPI()

    async def fake_sleep(delay: float) -> None:
        return None

    monkeypatch.setattr(realtime_sessions.api, "LiveKitAPI", lambda **kwargs: client)
    monkeypatch.setattr(realtime_sessions.asyncio, "sleep", fake_sleep)

    dispatched = await dispatch_agent(
        server_url="wss://livekit.example",
        api_key="key",
        api_secret="secret",
        room_name="realtime-test",
        agent_name="liveportrait-test",
        max_attempts=2,
        retry_delay_seconds=0,
    )

    assert dispatched is False
    assert client.agent_dispatch.create_attempts == 2
    assert client.closed is True
