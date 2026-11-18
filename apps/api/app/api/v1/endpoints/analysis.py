"""Owner-only Baymax AI request and analysis endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import cast

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.ai.classifier import BaymaxIntentClassifier, IntentClassificationError
from app.ai.engine import BaymaxAIEngine
from app.ai.generator import AnalysisGenerationError, BaymaxAnalysisGenerator
from app.auth.security import SESSION_COOKIE_NAME, verify_session_token
from app.core.config import Settings
from app.market_data.candles import (
    BinanceInterval,
    HistoricalCandleSeries,
    expected_open_times,
)
from app.market_data.freshness import MarketDataUnavailable
from app.orchestration.requests import (
    AnalysisInputUnavailable,
    AnalysisRequest,
    BaymaxRequestOrchestrator,
    PreparedAnalysisInput,
)

router = APIRouter(prefix="/analysis", tags=["Analysis"])


class HistoricalAnalysisRequest(BaseModel):
    """Explicit bounded historical OHLCV range request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1, max_length=30)
    interval: BinanceInterval
    start_time: datetime
    end_time: datetime

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized.isalnum():
            raise ValueError("Symbol must contain only letters and digits")
        return normalized

    @model_validator(mode="after")
    def validate_range(self) -> HistoricalAnalysisRequest:
        if self.start_time.tzinfo is None or self.end_time.tzinfo is None:
            raise ValueError("Historical range timestamps must include a timezone")
        if self.start_time > self.end_time:
            raise ValueError("Historical range start must not be after end")
        opens = expected_open_times(
            self.start_time,
            self.end_time,
            self.interval,
            max_count=10_000,
        )
        if not opens:
            raise ValueError("Historical range must contain at least one candle")
        return self


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


@router.post("/history", response_model=HistoricalCandleSeries)
async def fetch_historical_market_data(
    payload: HistoricalAnalysisRequest,
    request: Request,
) -> HistoricalCandleSeries:
    """Fetch a bounded, validated Binance Spot OHLCV series for the owner."""
    _require_owner(request)
    try:
        return cast(
            HistoricalCandleSeries,
            await request.app.state.historical_market_data_service.fetch(
                payload.symbol,
                payload.interval,
                start_time=payload.start_time,
                end_time=payload.end_time,
            ),
        )
    except MarketDataUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verified historical market data is temporarily unavailable.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
