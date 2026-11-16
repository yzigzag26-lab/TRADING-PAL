"""Owner-only request preparation endpoint for the analysis pipeline."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, HTTPException, Request, status

from app.auth.security import SESSION_COOKIE_NAME, verify_session_token
from app.core.config import Settings
from app.orchestration.requests import (
    AnalysisInputUnavailable,
    AnalysisRequest,
    BaymaxRequestOrchestrator,
    PreparedAnalysisInput,
)

router = APIRouter(prefix="/analysis", tags=["Analysis"])


@router.post("/prepare", response_model=PreparedAnalysisInput)
async def prepare_analysis(
    payload: AnalysisRequest,
    request: Request,
) -> PreparedAnalysisInput:
    """Prepare verified inputs for analysis; this endpoint does not generate advice."""
    settings = cast(Settings, request.app.state.settings)
    if not verify_session_token(
        request.cookies.get(SESSION_COOKIE_NAME),
        settings.session_secret,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
        )

    orchestrator = BaymaxRequestOrchestrator(
        request.app.state.market_data_service,
        clock_health_provider=request.app.state.clock_health_provider,
    )
    try:
        result = await orchestrator.prepare(payload)
    except AnalysisInputUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return result
