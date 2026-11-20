"""Explicit request-intent orchestration for analysis input preparation."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.market_data.freshness import MarketDataUnavailable
from app.market_data.models import ValidatedPrice
from app.market_data.provenance import PriceSnapshotRecorder
from app.market_data.service import BinanceMarketDataService

RequestIntent = Literal["educational", "programming", "current_market", "historical_market"]


class AnalysisRequest(BaseModel):
    """Structured request classification supplied by the trusted AI/application layer.

    This model deliberately does not guess intent from free text. The future AI
    intent classifier must map its result to this explicit contract before data
    retrieval is considered.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    message: str = Field(min_length=1, max_length=4_000)
    intent: RequestIntent
    symbol: str | None = Field(default=None, min_length=1, max_length=30)
    decision_requested: bool = False

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if not normalized.isalnum():
            raise ValueError("symbol must contain only letters and digits")
        return normalized

    @model_validator(mode="after")
    def validate_market_symbol(self) -> AnalysisRequest:
        if self.intent == "current_market" and self.symbol is None:
            raise ValueError("symbol is required for current-market requests")
        return self


class PreparedAnalysisInput(BaseModel):
    """Data-preparation result passed to the later AI analysis engine."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: RequestIntent
    market_data_required: bool
    market_data_status: Literal[
        "not_required", "ready", "historical_not_implemented", "decision_blocked"
    ]
    current_price: ValidatedPrice | None = None
    market_snapshot_id: UUID | None = None


class AnalysisInputUnavailable(Exception):
    """Raised when a required current-market input cannot be verified safely."""


class BaymaxRequestOrchestrator:
    """Prepare only the data required by an explicitly classified request.

    This is the input-orchestration boundary, not the AI response generator.
    Educational/programming requests never touch Binance. Historical retrieval
    remains a separate, not-yet-implemented path. Current-market requests must
    pass the verified clock-health provider and the market-data freshness gate.
    """

    def __init__(
        self,
        market_data: BinanceMarketDataService,
        *,
        clock_health_provider: Callable[[], bool],
        provenance_repository: PriceSnapshotRecorder | None = None,
        require_provenance: bool = False,
        allow_trading_decisions: bool = False,
    ) -> None:
        self._market_data = market_data
        self._clock_health_provider = clock_health_provider
        self._provenance_repository = provenance_repository
        self._require_provenance = require_provenance
        self._allow_trading_decisions = allow_trading_decisions

    async def prepare(
        self,
        request: AnalysisRequest,
        *,
        request_id: UUID | None = None,
    ) -> PreparedAnalysisInput:
        """Resolve required inputs and persist the exact validated market snapshot."""
        if request.intent in {"educational", "programming"}:
            return PreparedAnalysisInput(
                intent=request.intent,
                market_data_required=False,
                market_data_status="not_required",
            )

        if request.intent == "historical_market":
            return PreparedAnalysisInput(
                intent=request.intent,
                market_data_required=False,
                market_data_status="historical_not_implemented",
            )

        if request.decision_requested and not self._allow_trading_decisions:
            return PreparedAnalysisInput(
                intent=request.intent,
                market_data_required=True,
                market_data_status="decision_blocked",
            )

        if request.symbol is None:
            raise AnalysisInputUnavailable("A symbol is required for current-market analysis")
        if self._require_provenance and self._provenance_repository is None:
            raise AnalysisInputUnavailable(
                "Persistent market-data provenance is not configured; analysis is blocked."
            )

        try:
            price = await self._market_data.get_current_price(
                request.symbol,
                clock_healthy=self._clock_health_provider(),
            )
        except MarketDataUnavailable as exc:
            raise AnalysisInputUnavailable(
                "Verified current market data is unavailable; analysis is blocked"
            ) from exc

        snapshot_id: UUID | None = None
        if self._provenance_repository is not None:
            try:
                snapshot_id = await asyncio.to_thread(
                    self._provenance_repository.record_price,
                    price,
                    request_id=request_id,
                )
            except Exception as exc:
                raise AnalysisInputUnavailable(
                    "Validated market data could not be persisted for audit."
                ) from exc
        elif self._require_provenance:
            raise AnalysisInputUnavailable(
                "Persistent market-data provenance is not configured; analysis is blocked."
            )

        return PreparedAnalysisInput(
            intent=request.intent,
            market_data_required=True,
            market_data_status="ready",
            current_price=price,
            market_snapshot_id=snapshot_id,
        )
