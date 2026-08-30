import asyncio
import json
import logging
import re
import uuid
from datetime import timedelta

import httpx
from fastapi import APIRouter, BackgroundTasks, Request, status
from livekit import api
from livekit.protocol import agent_dispatch

from app.api.dependencies import AppSettings, CsrfProtected, CurrentUser, DbSession, Storage
from app.core.errors import ApiError
from app.schemas.realtime_sessions import RealtimeSessionCreate, RealtimeSessionResponse
from app.services import portrait_service

router = APIRouter(prefix="/realtime-sessions", tags=["realtime-sessions"])
logger = logging.getLogger(__name__)

REALTIME_AGENT_NAME_PREFIX = "liveportrait"
RUNPOD_PODS_URL = "https://rest.runpod.io/v1/pods"
RUNPOD_IMMUTABLE_IMAGE_PATTERN = re.compile(
    r"^[^\s:]+(?:/[^\s:]+)*:realtime-(?:latest|[A-Za-z0-9._-]+)$"
)
RUNPOD_ERROR_MESSAGE_MAX_LENGTH = 500
DISPATCH_MAX_ATTEMPTS = 60
DISPATCH_RETRY_DELAY_SECONDS = 2.0


def create_agent_name(session_id: uuid.UUID) -> str:
    return f"{REALTIME_AGENT_NAME_PREFIX}-{session_id}"


def get_runpod_error_message(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None

    candidates: list[object] = []
    if isinstance(payload, dict):
        candidates.extend((payload.get("error"), payload.get("message")))

    for candidate in candidates:
        if isinstance(candidate, dict):
            candidate = candidate.get("message")
        if isinstance(candidate, str) and candidate.strip():
            return " ".join(candidate.split())[:RUNPOD_ERROR_MESSAGE_MAX_LENGTH]
    return None


def classify_runpod_creation_error(
    status_code: int,
    provider_message: str | None,
) -> tuple[str, str]:
    message = (provider_message or "").lower()
    if status_code in {401, 403}:
        return (
            "RUNPOD_AUTH_FAILED",
            "The realtime worker provider is not configured correctly.",
        )
    if status_code == 429:
        return (
            "RUNPOD_RATE_LIMITED",
            "The realtime worker provider is busy. Please try again shortly.",
        )
    if any(term in message for term in ("balance", "billing", "credit", "fund")):
        return (
            "RUNPOD_BILLING_UNAVAILABLE",
            "The realtime worker provider account is unavailable.",
        )
    if any(term in message for term in ("capacity", "gpu", "instance", "stock")):
        return (
            "RUNPOD_CAPACITY_UNAVAILABLE",
            "No realtime GPU is currently available. Please try again shortly.",
        )
    if "image" in message:
        return (
            "RUNPOD_IMAGE_UNAVAILABLE",
            "The realtime worker image is unavailable.",
        )
    return (
        "RUNPOD_POD_CREATION_REJECTED",
        "The realtime worker could not be provisioned.",
    )


async def create_runpod_pod(
    settings: AppSettings,
    session_id: uuid.UUID,
    agent_name: str,
) -> str:
    if not settings.RUNPOD_API_KEY:
        raise ApiError(503, "RUNPOD_UNCONFIGURED", "Runpod API key is not configured.")

    image_name = settings.RUNPOD_REALTIME_IMAGE.strip()
    if not RUNPOD_IMMUTABLE_IMAGE_PATTERN.fullmatch(image_name):
        logger.error(
            "realtime_image_invalid image=%s expected_tag=sha-<12 lowercase hex>",
            image_name,
        )
        raise ApiError(
            503,
            "RUNPOD_IMAGE_INVALID",
            "The realtime worker image is not configured correctly.",
        )

    pod_name = f"mimicmotion-realtime-{session_id}"
    payload = {
        "name": pod_name,
        "imageName": image_name,
        "gpuTypeIds": ["NVIDIA L40S"],
        "gpuCount": 1,
        "containerDiskInGb": 100,
        "volumeInGb": 40,
        "volumeMountPath": "/workspace",
        "ports": ["8081/http"],
        "cloudType": "SECURE",
        "env": {
            "LIVEKIT_URL": settings.LIVEKIT_URL,
            "LIVEKIT_API_KEY": settings.LIVEKIT_API_KEY,
            "LIVEKIT_API_SECRET": settings.LIVEKIT_API_SECRET,
            "LIVEKIT_AGENT_NAME": agent_name,
        },
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                RUNPOD_PODS_URL,
                headers={
                    "Authorization": f"Bearer {settings.RUNPOD_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30.0,
            )
    except httpx.TimeoutException as exc:
        logger.warning(
            "realtime_pod_creation_timed_out session_id=%s image=%s",
            session_id,
            image_name,
        )
        raise ApiError(
            503,
            "RUNPOD_TIMEOUT",
            "The realtime worker provider timed out. Please try again.",
        ) from exc
    except httpx.RequestError as exc:
        logger.warning(
            "realtime_pod_creation_request_failed session_id=%s image=%s error_type=%s",
            session_id,
            image_name,
            type(exc).__name__,
        )
        raise ApiError(
            503,
            "RUNPOD_UNAVAILABLE",
            "The realtime worker provider is unavailable. Please try again.",
        ) from exc

    if response.status_code >= 400:
        provider_message = get_runpod_error_message(response)
        error_code, user_message = classify_runpod_creation_error(
            response.status_code,
            provider_message,
        )
        logger.error(
            "realtime_pod_creation_rejected session_id=%s image=%s "
            "provider_status=%s error_code=%s provider_message=%s",
            session_id,
            image_name,
            response.status_code,
            error_code,
            provider_message or "unavailable",
        )
        raise ApiError(
            503,
            error_code,
            user_message,
            details={"provider_status": response.status_code},
        )

    try:
        data = response.json()
    except ValueError as exc:
        logger.error(
            "realtime_pod_creation_invalid_response session_id=%s image=%s reason=invalid_json",
            session_id,
            image_name,
        )
        raise ApiError(
            502,
            "RUNPOD_RESPONSE_INVALID",
            "The realtime worker provider returned an invalid response.",
        ) from exc

    pod_id = data.get("id") if isinstance(data, dict) else None
    if not isinstance(pod_id, str) or not pod_id:
        logger.error(
            "realtime_pod_creation_invalid_response session_id=%s image=%s reason=missing_pod_id",
            session_id,
            image_name,
        )
        raise ApiError(
            502,
            "RUNPOD_RESPONSE_INVALID",
            "The realtime worker provider returned an invalid response.",
        )
    return pod_id


async def terminate_runpod_pod(settings: AppSettings, pod_id: str) -> None:
    if not settings.RUNPOD_API_KEY:
        return

    async with httpx.AsyncClient() as client:
        # First, stop the pod
        stop_response = await client.post(
            f"https://rest.runpod.io/v1/pods/{pod_id}/stop",
            headers={"Authorization": f"Bearer {settings.RUNPOD_API_KEY}"},
            timeout=30.0,
        )
        if stop_response.status_code >= 400:
            print(f"Warning: Failed to stop Runpod {pod_id}: {stop_response.text}")

        # Wait a bit before terminating to allow Runpod to process the stop command
        await asyncio.sleep(5)

        # Then, terminate the pod explicitly
        terminate_response = await client.delete(
            f"https://rest.runpod.io/v1/pods/{pod_id}",
            headers={"Authorization": f"Bearer {settings.RUNPOD_API_KEY}"},
            timeout=30.0,
        )
        if terminate_response.status_code >= 400:
            print(f"Warning: Failed to terminate Runpod {pod_id}: {terminate_response.text}")


def create_participant_token(
    *,
    api_key: str,
    api_secret: str,
    room_name: str,
    identity: str,
    metadata: str,
    ttl_seconds: int,
) -> str:
    return (
        api.AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_name("Browser")
        .with_metadata(metadata)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .with_ttl(timedelta(seconds=ttl_seconds))
        .to_jwt()
    )


def create_viewer_token(
    *,
    api_key: str,
    api_secret: str,
    room_name: str,
    identity: str,
    ttl_seconds: int,
) -> str:
    return (
        api.AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_name("Read-only Viewer")
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=False,
                can_subscribe=True,
                can_publish_data=False,
            )
        )
        .with_ttl(timedelta(seconds=ttl_seconds))
        .to_jwt()
    )


async def dispatch_agent(
    server_url: str,
    api_key: str,
    api_secret: str,
    room_name: str,
    agent_name: str,
    *,
    max_attempts: int = DISPATCH_MAX_ATTEMPTS,
    retry_delay_seconds: float = DISPATCH_RETRY_DELAY_SECONDS,
) -> bool:
    livekit_api = api.LiveKitAPI(url=server_url, api_key=api_key, api_secret=api_secret)
    try:
        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                try:
                    dispatches = await livekit_api.agent_dispatch.list_dispatch(room_name)
                    if any(
                        dispatch.agent_name == agent_name and not dispatch.state.deleted_at
                        for dispatch in dispatches
                    ):
                        logger.info(
                            "realtime_agent_dispatch_already_exists",
                            extra={"room_name": room_name, "agent_name": agent_name},
                        )
                        return True
                except Exception:
                    # The room or agent may not exist yet while the pod is starting.
                    pass

            try:
                await livekit_api.agent_dispatch.create_dispatch(
                    agent_dispatch.CreateAgentDispatchRequest(
                        agent_name=agent_name,
                        room=room_name,
                    )
                )
                logger.info(
                    "realtime_agent_dispatched",
                    extra={
                        "room_name": room_name,
                        "agent_name": agent_name,
                        "attempt": attempt,
                    },
                )
                return True
            except Exception as exc:
                if attempt == max_attempts:
                    logger.exception(
                        "realtime_agent_dispatch_failed",
                        extra={
                            "room_name": room_name,
                            "agent_name": agent_name,
                            "attempts": max_attempts,
                        },
                    )
                    return False
                if attempt == 1 or attempt % 10 == 0:
                    logger.warning(
                        "realtime_agent_dispatch_retry",
                        extra={
                            "room_name": room_name,
                            "agent_name": agent_name,
                            "attempt": attempt,
                            "error": str(exc),
                        },
                    )
                await asyncio.sleep(retry_delay_seconds)
    finally:
        await livekit_api.aclose()

    return False


async def dispatch_or_terminate_pod(
    *,
    settings: AppSettings,
    pod_id: str,
    room_name: str,
    agent_name: str,
) -> None:
    dispatched = await dispatch_agent(
        server_url=settings.LIVEKIT_URL or "",
        api_key=settings.LIVEKIT_API_KEY or "",
        api_secret=settings.LIVEKIT_API_SECRET or "",
        room_name=room_name,
        agent_name=agent_name,
    )
    if dispatched:
        return

    try:
        await terminate_runpod_pod(settings, pod_id)
    except Exception:
        logger.exception(
            "realtime_pod_cleanup_after_dispatch_failure_failed",
            extra={"pod_id": pod_id, "room_name": room_name},
        )


@router.post("", response_model=RealtimeSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_realtime_session(
    payload: RealtimeSessionCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    storage: Storage,
    settings: AppSettings,
    _csrf: CsrfProtected,
) -> RealtimeSessionResponse:
    if not settings.LIVEKIT_URL or not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        raise ApiError(503, "REALTIME_UNAVAILABLE", "Realtime animation is not configured.")

    portrait = await portrait_service.get_portrait(db, storage, user, payload.portrait_id)
    session_id = uuid.uuid4()
    agent_name = create_agent_name(session_id)

    # Give each on-demand worker a unique name so LiveKit routes this session to its pod.
    pod_id = await create_runpod_pod(settings, session_id, agent_name)

    room_name = f"realtime-{session_id}"
    identity = f"user-{user.id}"
    metadata = json.dumps(
        {
            "session_id": str(session_id),
            "portrait_id": str(payload.portrait_id),
            "portrait_url": portrait.image_url,
            "request_id": request.state.request_id,
        },
        separators=(",", ":"),
    )
    token = create_participant_token(
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
        room_name=room_name,
        identity=identity,
        metadata=metadata,
        ttl_seconds=settings.LIVEKIT_TOKEN_TTL_SECONDS,
    )
    viewer_token = create_viewer_token(
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
        room_name=room_name,
        identity=f"viewer-{uuid.uuid4()}",
        ttl_seconds=settings.LIVEKIT_TOKEN_TTL_SECONDS,
    )
    background_tasks.add_task(
        dispatch_or_terminate_pod,
        settings=settings,
        pod_id=pod_id,
        room_name=room_name,
        agent_name=agent_name,
    )
    return RealtimeSessionResponse(
        session_id=session_id,
        room_name=room_name,
        server_url=settings.LIVEKIT_URL,
        participant_token=token,
        viewer_token=viewer_token,
        expires_in_seconds=settings.LIVEKIT_TOKEN_TTL_SECONDS,
        pod_id=pod_id,
    )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def terminate_realtime_session(
    session_id: uuid.UUID,
    user: CurrentUser,
    settings: AppSettings,
    _csrf: CsrfProtected,
    pod_id: str | None = None,
) -> None:
    # Terminate the pod synchronously to ensure it completes even if Railway restarts
    if pod_id:
        try:
            await terminate_runpod_pod(settings, pod_id)
        except Exception as e:
            # Log but don't fail the request - user has already disconnected
            print(f"Error terminating pod {pod_id}: {e}")
