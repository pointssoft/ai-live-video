from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.dependencies import get_storage
from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.session import SessionFactory
from app.middleware.error_handler import api_error_handler
from app.middleware.request_id import RequestIdMiddleware

settings = get_settings()
app = FastAPI(title="MimicMotion API", version="0.1.0")
app.add_middleware(RequestIdMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Idempotency-Key", "X-CSRF-Token", "X-Request-ID"],
    expose_headers=["Idempotency-Replayed", "X-Request-ID"],
)
app.add_exception_handler(ApiError, api_error_handler)
app.include_router(v1_router)


@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok", "service": "api"}


@app.get("/health/ready")
async def ready() -> JSONResponse:
    checks = {"database": "ok", "storage": "ok"}
    try:
        async with SessionFactory() as db:
            await db.execute(text("SELECT 1"))
    except Exception:
        checks["database"] = "failed"
    if settings.READY_CHECK_STORAGE:
        try:
            await get_storage().check_bucket_access()
        except Exception:
            checks["storage"] = "failed"
    is_ready = all(value == "ok" for value in checks.values())
    return JSONResponse(
        status_code=status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ready" if is_ready else "not_ready", "checks": checks},
    )
