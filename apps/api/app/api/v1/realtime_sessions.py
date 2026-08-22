import json
import uuid
from datetime import timedelta

from fastapi import APIRouter, Request, status
from livekit import api

from app.api.dependencies import AppSettings, CsrfProtected, CurrentUser, DbSession, Storage
from app.core.errors import ApiError
from app.schemas.realtime_sessions import RealtimeSessionCreate, RealtimeSessionResponse
from app.services import portrait_service

router = APIRouter(prefix="/realtime-sessions", tags=["realtime-sessions"])


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


@router.post("", response_model=RealtimeSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_realtime_session(
    payload: RealtimeSessionCreate,
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
    return RealtimeSessionResponse(
        session_id=session_id,
        room_name=room_name,
        server_url=settings.LIVEKIT_URL,
        participant_token=token,
        expires_in_seconds=settings.LIVEKIT_TOKEN_TTL_SECONDS,
    )
