"""Version 1 API router."""

from fastapi import APIRouter

from app.api.v1.endpoints.analysis import router as analysis_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.diagnostics import router as diagnostics_router
from app.api.v1.endpoints.durable_snapshot import router as durable_snapshot_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.websocket_rotation import router as websocket_rotation_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(analysis_router)
api_router.include_router(auth_router)
api_router.include_router(diagnostics_router)
api_router.include_router(durable_snapshot_router)
api_router.include_router(websocket_rotation_router)
