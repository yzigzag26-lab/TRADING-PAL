"""Version 1 API router."""

from fastapi import APIRouter

from app.api.v1.endpoints.analysis import router as analysis_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.diagnostics import router as diagnostics_router
from app.api.v1.endpoints.health import router as health_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(analysis_router)
api_router.include_router(auth_router)
api_router.include_router(diagnostics_router)
