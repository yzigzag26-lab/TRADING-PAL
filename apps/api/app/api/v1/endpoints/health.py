"""Public liveness endpoint."""

from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter(tags=["System"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check API liveness",
    description=(
        "Returns the API process liveness status. This endpoint does not check "
        "database, authentication-provider, or third-party service availability."
    ),
)
async def health_check() -> HealthResponse:
    """Return a minimal liveness response without infrastructure details."""
    return HealthResponse(status="ok", service="baymax-api", version="0.1.0")
