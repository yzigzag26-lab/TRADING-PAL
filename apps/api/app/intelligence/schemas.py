"""Typed, validated contracts for the Gate 4 market-intelligence engine.

Every model is frozen and rejects unknown fields so the AI reasoning layer and
the API surface consume one explicit, auditable structure.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

TrendDirection = Literal["bullish", "bearish", "ranging", "transitioning", "uncertain"]
VolatilityLevel = Literal["low", "normal", "high"]
VolatilityDirection = Literal["expanding", "contracting", "stable"]
ZoneSide = Literal["support", "resistance"]
DataQuality = Literal["complete", "partial", "insufficient"]
IntelligenceReadiness = Literal["ready", "degraded", "blocked"]
AlignmentStatus = Literal[
    "aligned_bullish", "aligned_bearish", "partial", "conflicting", "insufficient"
]
StructureKind = Literal[
    "higher_high",
    "higher_low",
    "lower_high",
    "lower_low",
    "break_of_structure",
    "change_of_character",
    "consolidation",
    "breakout",
    "failed_breakout",
]


class IndicatorReading(BaseModel):
    """One deterministic indicator result at the latest closed candle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=40)
    parameters: dict[str, int | float] = Field(default_factory=dict)
    values: dict[str, float]
    candle_count: int = Field(ge=0)
    warmup_candles: int = Field(ge=0)
    sufficient_history: bool
    latest_input_open_time: datetime | None = None
    calculated_at: datetime


class TrendAssessment(BaseModel):
    """Evidence-scored trend classification for one timeframe."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    direction: TrendDirection
    score: float = Field(ge=-1.0, le=1.0)
    evidence: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()


class StructureFinding(BaseModel):
    """A confirmed deterministic market-structure observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: StructureKind
    detail: str = Field(min_length=1, max_length=500)
    reference_open_times: tuple[datetime, ...] = ()
    confirmed: bool


class PriceZone(BaseModel):
    """A support or resistance zone derived from validated candles."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    side: ZoneSide
    lower: Decimal
    upper: Decimal
    timeframe: str
    method: str = Field(min_length=1, max_length=80)
    touches: int = Field(ge=1)
    strength: float = Field(ge=0.0, le=1.0)
    active: bool
    source_open_times: tuple[datetime, ...] = ()
    invalidated_reason: str | None = Field(default=None, max_length=300)


class VolatilityAssessment(BaseModel):
    """Deterministic volatility classification for one timeframe."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    level: VolatilityLevel
    direction: VolatilityDirection
    atr: float | None = None
    atr_percent: float | None = None
    bollinger_width: float | None = None
    bollinger_width_percentile: float | None = None
    evidence: tuple[str, ...] = ()


class TimeframeAnalysis(BaseModel):
    """Complete deterministic analysis of one validated candle series."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    interval: str
    symbol: str
    snapshot_id: UUID | None = None
    candle_count: int = Field(ge=0)
    closed_candle_count: int = Field(ge=0)
    series_complete: bool
    last_closed_open_time: datetime | None = None
    last_closed_close: Decimal | None = None
    indicators: tuple[IndicatorReading, ...] = ()
    trend: TrendAssessment
    structure: tuple[StructureFinding, ...] = ()
    zones: tuple[PriceZone, ...] = ()
    volatility: VolatilityAssessment
    usable: bool
    limitations: tuple[str, ...] = ()


class TimeframeAlignment(BaseModel):
    """Cross-timeframe agreement summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: AlignmentStatus
    directions: dict[str, TrendDirection]
    notes: tuple[str, ...] = ()


class MarketIntelligenceReport(BaseModel):
    """Structured market intelligence consumed by strategy and the AI layer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    exchange: Literal["BINANCE"] = "BINANCE"
    market: Literal["SPOT"] = "SPOT"
    analyzed_at: datetime
    current_price: str
    current_price_snapshot_id: UUID | None = None
    timeframe_analyses: tuple[TimeframeAnalysis, ...] = ()
    alignment: TimeframeAlignment
    data_quality: DataQuality
    missing_inputs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    readiness: IntelligenceReadiness


__all__ = [
    "AlignmentStatus",
    "DataQuality",
    "IndicatorReading",
    "IntelligenceReadiness",
    "MarketIntelligenceReport",
    "PriceZone",
    "StructureFinding",
    "StructureKind",
    "TimeframeAlignment",
    "TimeframeAnalysis",
    "TrendAssessment",
    "TrendDirection",
    "VolatilityAssessment",
    "VolatilityDirection",
    "VolatilityLevel",
    "ZoneSide",
]
