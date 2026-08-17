import hmac

from fastapi import APIRouter, Header, Request, status
from pydantic import ValidationError

from app.api.dependencies import AppSettings, DbSession, Storage
from app.core.errors import ApiError
from app.schemas.webhooks import RunpodWebhookPayload
from app.services.runpod import RunpodClient
from app.services.runpod_webhooks import ingest_runpod_webhook

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/runpod", status_code=status.HTTP_202_ACCEPTED)
async def receive_runpod_webhook(
    request: Request,
    db: DbSession,
    storage: Storage,
    settings: AppSettings,
    webhook_token: str | None = Header(default=None, alias="X-Runpod-Webhook-Token"),
) -> dict[str, bool]:
    if not settings.RUNPOD_WEBHOOK_TOKEN:
        raise ApiError(503, "WEBHOOK_NOT_CONFIGURED", "The provider webhook is not configured.")
    provided_token = webhook_token or request.query_params.get("token")
    if not provided_token or not hmac.compare_digest(
        provided_token, settings.RUNPOD_WEBHOOK_TOKEN
    ):
        raise ApiError(401, "WEBHOOK_UNAUTHORIZED", "The provider webhook is not authorized.")

    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit():
        if int(content_length) > settings.RUNPOD_WEBHOOK_MAX_BODY_BYTES:
            raise ApiError(413, "WEBHOOK_BODY_TOO_LARGE", "The webhook body is too large.")
    raw_body = await request.body()
    if len(raw_body) > settings.RUNPOD_WEBHOOK_MAX_BODY_BYTES:
        raise ApiError(413, "WEBHOOK_BODY_TOO_LARGE", "The webhook body is too large.")
    try:
        payload = RunpodWebhookPayload.model_validate_json(raw_body)
    except ValidationError as exc:
        raise ApiError(400, "WEBHOOK_PAYLOAD_INVALID", "The webhook payload is invalid.") from exc

    if not settings.RUNPOD_API_KEY or not settings.RUNPOD_ENDPOINT_ID:
        raise ApiError(503, "RUNPOD_NOT_CONFIGURED", "The generation provider is not configured.")
    runpod = RunpodClient(settings)
    try:
        processed = await ingest_runpod_webhook(
            db, storage, settings, runpod, payload, raw_body
        )
    finally:
        await runpod.close()
    if not processed:
        raise ApiError(
            503,
            "WEBHOOK_PROCESSING_DEFERRED",
            "The provider webhook could not be processed yet.",
        )
    return {"accepted": True}
