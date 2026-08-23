import json
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


async def create_runpod_pod(settings: AppSettings, session_id: uuid.UUID) -> str:
    if not settings.RUNPOD_API_KEY:
        raise ApiError(500, "RUNPOD_UNCONFIGURED", "Runpod API key is not configured.")
    # You would pass specific configuration that matches your deploy-realtime-worker logic
    pod_name = f"mimicmotion-realtime-{session_id}"
    image_name = "malaknoyn/mimicmotion-realtime-worker:sha-8d5d5b57a201"
    
    payload = {
        "name": pod_name,
        "imageName": image_name,
        "gpuTypeIds": ["NVIDIA H100 SXM"],
        "gpuCount": 1,
        "containerDiskInGb": 100,
        "volumeInGb": 40,
        "volumeMountPath": "/workspace",
        "ports": ["8081/http"],
        "env": {
            "LIVEKIT_URL": settings.LIVEKIT_URL,
            "LIVEKIT_API_KEY": settings.LIVEKIT_API_KEY,
            "LIVEKIT_API_SECRET": settings.LIVEKIT_API_SECRET,
            "LIVEKIT_AGENT_NAME": "liveportrait",
        }
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.runpod.io/v2/pods",
            headers={
                "Authorization": f"Bearer {settings.RUNPOD_API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=30.0
        )
        if response.status_code >= 400:
            raise ApiError(500, "RUNPOD_POD_CREATION_FAILED", f"Failed to create pod: {response.text}")
        
        data = response.json()
        return data["id"]


async def terminate_runpod_pod(settings: AppSettings, pod_id: str) -> None:
    if not settings.RUNPOD_API_KEY:
        return
    
    async with httpx.AsyncClient() as client:
        await client.delete(
            f"https://api.runpod.io/v2/pods/{pod_id}",
            headers={
                "Authorization": f"Bearer {settings.RUNPOD_API_KEY}"
            },
            timeout=30.0
        )


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
) -> None:
    livekit_api = api.LiveKitAPI(url=server_url, api_key=api_key, api_secret=api_secret)
    try:
        await livekit_api.agent_dispatch.create_dispatch(
            agent_dispatch.CreateAgentDispatchRequest(
                agent_name=agent_name,
                room=room_name,
            )
        )
    finally:
        await livekit_api.aclose()


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
    
    # Create an on-demand Runpod WebRTC Pod
    pod_id = await create_runpod_pod(settings, session_id)
    
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
    background_tasks.add_task(
        dispatch_agent,
        server_url=settings.LIVEKIT_URL,
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
        room_name=room_name,
        agent_name="liveportrait",
    )
    return RealtimeSessionResponse(
        session_id=session_id,
        room_name=room_name,
        server_url=settings.LIVEKIT_URL,
        participant_token=token,
        expires_in_seconds=settings.LIVEKIT_TOKEN_TTL_SECONDS,
        pod_id=pod_id,
    )

@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def terminate_realtime_session(
    session_id: uuid.UUID,
    pod_id: str,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    settings: AppSettings,
    _csrf: CsrfProtected,
) -> None:
    # Schedule the termination task to run in the background
    background_tasks.add_task(terminate_runpod_pod, settings, pod_id)

