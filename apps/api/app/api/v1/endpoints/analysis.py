"""Owner-only Baymax AI request and analysis endpoints."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.ai.classifier import BaymaxIntentClassifier, IntentClassificationError
from app.ai.engine import BaymaxAIEngine
from app.ai.generator import AnalysisGenerationError, BaymaxAnalysisGenerator
from app.auth.security import SESSION_COOKIE_NAME, verify_session_token
from app.core.config import Settings
from app.orchestration.requests import (
    AnalysisInputUnavailable,
    AnalysisRequest,
    BaymaxRequestOrchestrator,
    PreparedAnalysisInput,
)

router = APIRouter(prefix="/analysis", tags=["Analysis"])


class AnalysisConversationRequest(BaseModel):
    """Natural-language message accepted by the owner-only AI endpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    message: str = Field(min_length=1, max_length=4_000)


class AnalysisConversationResponse(BaseModel):
    """Structured response envelope returned by Baymax."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    answer: str
    intent: str
    symbol: str | None
    market_data_status: str
    needs_clarification: bool


def _require_owner(request: Request) -> Settings:
    settings = cast(Settings, request.app.state.settings)
    if not verify_session_token(
        request.cookies.get(SESSION_COOKIE_NAME),
        settings.session_secret,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
        )
    return settings


@router.post("/prepare", response_model=PreparedAnalysisInput)
async def prepare_analysis(
    payload: AnalysisRequest,
    request: Request,
) -> PreparedAnalysisInput:
    """Prepare verified inputs for internal use; this endpoint does not generate advice."""
    _require_owner(request)
    orchestrator = BaymaxRequestOrchestrator(
        request.app.state.market_data_service,
        clock_health_provider=request.app.state.clock_health_provider,
    )
    try:
        return await orchestrator.prepare(payload)
    except AnalysisInputUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.post("/respond", response_model=AnalysisConversationResponse)
async def respond_to_message(
    payload: AnalysisConversationRequest,
    request: Request,
) -> AnalysisConversationResponse:
    """Classify, prepare verified inputs, and generate an owner-only AI response."""
    settings = _require_owner(request)
    if not settings.groq_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI provider is not configured on this deployment.",
        )

    client = request.app.state.groq_client
    engine = BaymaxAIEngine(
        classifier=BaymaxIntentClassifier(client),
        generator=BaymaxAnalysisGenerator(client),
        orchestrator=BaymaxRequestOrchestrator(
            request.app.state.market_data_service,
            clock_health_provider=request.app.state.clock_health_provider,
        ),
    )
    try:
        result = await engine.respond(payload.message)
    except AnalysisInputUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verified current market data is unavailable; this analysis is blocked.",
        ) from exc
    except (IntentClassificationError, AnalysisGenerationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Baymax AI is temporarily unavailable. Please try again.",
        ) from exc

    return AnalysisConversationResponse(
        answer=result.answer,
        intent=result.intent,
        symbol=result.symbol,
        market_data_status=result.market_data_status,
        needs_clarification=result.needs_clarification,
    )
