from fastapi import APIRouter

from app.api.v1 import auth, generations, portraits, realtime_sessions, uploads, users, webhooks

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(uploads.router)
router.include_router(portraits.router)
router.include_router(realtime_sessions.router)
router.include_router(generations.router)
router.include_router(webhooks.router)
