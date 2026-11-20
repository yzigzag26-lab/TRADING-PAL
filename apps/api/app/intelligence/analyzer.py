"""Gate 4 deterministic market-intelligence engine.

Consumes only verified inputs — a fresh ``ValidatedPrice`` and validated,
closed-candle ``HistoricalCandleSeries`` per timeframe — and produces the
structured ``MarketIntelligenceReport`` consumed by strategy and the AI layer.
No network access, no Groq calls, no fabricated data.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.intelligence.indicators import compute_indicator_readings, indicator_value
from app.intelligence.schemas import (
    MarketIntelligenceReport,
    TimeframeAlignment,
    TimeframeAnalysis,
    TrendDirection,
    VolatilityAssessment,
)
from app.intelligence.structure import analyze_structure
from app.intelligence.trend import classify_trend
from app.intelligence.volatility import assess_volatility
from app.intelligence.zones import derive_zones
from app.market_data.candles import HistoricalCandleSeries
from app.market_data.models import ValidatedPrice

# Versioned Gate 4 analysis configuration.
ANALYSIS_TIMEFRAMES: tuple[str, ...] = ("5m", "15m", "1h", "4h", "1d")
MIN_USABLE_CANDLES = 60
MIN_ALIGNMENT_TIMEFRAMES = 3
HIGHER_TIMEFRAMES: tuple[str, ...] = ("4h", "1d")


@dataclass(frozen=True, slots=True)
class TimeframeSeriesInput:
    """One validated candle series with its provenance snapshot identity."""

    interval: str
    series: HistoricalCandleSeries
    snapshot_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class MarketIntelligenceInput:
    """Complete verified input bundle for one market-intelligence analysis."""

    price: ValidatedPrice
    price_snapshot_id: UUID | None
    timeframes: Mapping[str, TimeframeSeriesInput]
    historical_fetch_ms: float = 0.0


class MarketIntelligenceEngine:
    """Run deterministic per-timeframe and multi-timeframe analysis."""

    def analyze(
        self,
        bundle: MarketIntelligenceInput,
        *,
        analyzed_at: datetime | None = None,
    ) -> MarketIntelligenceReport:
        """Produce the structured intelligence report; never raises on bad data.

        Missing or unusable timeframes degrade the report instead of failing —
        the strategy and safety layers decide whether a recommendation is still
        defensible.
        """
        analyzed = (analyzed_at or datetime.now(UTC)).astimezone(UTC)
        analyses: list[TimeframeAnalysis] = []
        missing: list[str] = []
        limitations: list[str] = []

        for interval in ANALYSIS_TIMEFRAMES:
            entry = bundle.timeframes.get(interval)
            if entry is None:
                missing.append(f"timeframe:{interval}")
                limitations.append(f"No candle series supplied for {interval}")
                continue
            analyses.append(self._analyze_timeframe(entry, analyzed))

        usable = [item for item in analyses if item.usable]
        directions = {item.interval: item.trend.direction for item in analyses if item.usable}
        alignment = self._align(directions, len(usable))

        all_complete = len(analyses) == len(ANALYSIS_TIMEFRAMES) and all(
            item.series_complete for item in analyses
        )
        if len(usable) == 0:
            data_quality = "insufficient"
            readiness = "blocked"
        elif all_complete and len(usable) >= MIN_ALIGNMENT_TIMEFRAMES:
            data_quality = "complete"
            readiness = "ready" if alignment.status != "insufficient" else "degraded"
        else:
            data_quality = "partial"
            readiness = "degraded"

        for item in analyses:
            limitations.extend(f"{item.interval}: {note}" for note in item.limitations)

        return MarketIntelligenceReport(
            symbol=bundle.price.symbol,
            analyzed_at=analyzed,
            current_price=str(bundle.price.price),
            current_price_snapshot_id=bundle.price_snapshot_id,
            timeframe_analyses=tuple(analyses),
            alignment=alignment,
            data_quality=data_quality,  # type: ignore[arg-type]
            missing_inputs=tuple(missing),
            limitations=tuple(dict.fromkeys(limitations)),
            readiness=readiness,  # type: ignore[arg-type]
        )

    def _analyze_timeframe(
        self,
        entry: TimeframeSeriesInput,
        analyzed_at: datetime,
    ) -> TimeframeAnalysis:
        series = entry.series
        closed = tuple(candle for candle in series.candles if candle.is_closed)
        limitations: list[str] = []
        if not series.complete:
            limitations.append(
                f"Series incomplete: {len(series.missing_open_times)} missing intervals"
            )
        forming = len(series.candles) - len(closed)
        if forming:
            limitations.append(f"{forming} forming candle(s) excluded from analysis")
        if len(closed) < MIN_USABLE_CANDLES:
            limitations.append(
                f"Only {len(closed)} closed candles; minimum is {MIN_USABLE_CANDLES}"
            )

        usable = len(closed) >= MIN_USABLE_CANDLES
        indicators = compute_indicator_readings(closed, calculated_at=analyzed_at)
        trend = classify_trend(closed, indicators)
        atr_value = indicator_value(indicators, "ATR", "period", 14)
        structure = analyze_structure(closed, atr_value=atr_value) if usable else ()
        zones = (
            derive_zones(closed, timeframe=entry.interval, atr_value=atr_value) if usable else ()
        )
        volatility = (
            assess_volatility(closed, indicators)
            if usable
            else VolatilityAssessment(
                level="normal",
                direction="stable",
                evidence=("Timeframe below minimum usable candle count",),
            )
        )

        return TimeframeAnalysis(
            interval=entry.interval,
            symbol=series.symbol,
            snapshot_id=entry.snapshot_id,
            candle_count=len(series.candles),
            closed_candle_count=len(closed),
            series_complete=series.complete,
            last_closed_open_time=closed[-1].open_time if closed else None,
            last_closed_close=closed[-1].close if closed else None,
            indicators=indicators,
            trend=trend,
            structure=structure,
            zones=zones,
            volatility=volatility,
            usable=usable,
            limitations=tuple(limitations),
        )

    @staticmethod
    def _align(directions: Mapping[str, TrendDirection], usable_count: int) -> TimeframeAlignment:
        if usable_count < MIN_ALIGNMENT_TIMEFRAMES:
            return TimeframeAlignment(
                status="insufficient",
                directions=dict(directions),
                notes=(
                    f"Only {usable_count} usable timeframe(s); "
                    f"minimum is {MIN_ALIGNMENT_TIMEFRAMES}",
                ),
            )
        bullish = sum(1 for value in directions.values() if value == "bullish")
        bearish = sum(1 for value in directions.values() if value == "bearish")
        total = len(directions)
        notes: list[str] = []

        higher_dirs = [directions[t] for t in HIGHER_TIMEFRAMES if t in directions]
        lower_dirs = [directions[t] for t in directions if t not in HIGHER_TIMEFRAMES]
        if higher_dirs and lower_dirs:
            higher_bull = sum(1 for d in higher_dirs if d == "bullish")
            higher_bear = sum(1 for d in higher_dirs if d == "bearish")
            lower_bull = sum(1 for d in lower_dirs if d == "bullish")
            lower_bear = sum(1 for d in lower_dirs if d == "bearish")
            if (higher_bull and lower_bear) or (higher_bear and lower_bull):
                notes.append("Higher and lower timeframes disagree on direction")

        if bearish == 0 and bullish == total:
            return TimeframeAlignment(
                status="aligned_bullish", directions=dict(directions), notes=tuple(notes)
            )
        if bullish == 0 and bearish == total:
            return TimeframeAlignment(
                status="aligned_bearish", directions=dict(directions), notes=tuple(notes)
            )
        score = (bullish - bearish) / total
        if bullish > 0 and bearish > 0:
            return TimeframeAlignment(
                status="conflicting",
                directions=dict(directions),
                notes=tuple(notes) or ("Bullish and bearish timeframe signals conflict",),
            )
        if score >= 0.5:
            status = "partial"
            notes = list(notes) + ["Partial bullish alignment across timeframes"]
        elif score <= -0.5:
            status = "partial"
            notes = list(notes) + ["Partial bearish alignment across timeframes"]
        else:
            status = "conflicting"
            notes = list(notes) + ["Timeframe directions do not form a coherent bias"]
        return TimeframeAlignment(
            status=status,  # type: ignore[arg-type]
            directions=dict(directions),
            notes=tuple(notes),
        )


__all__ = [
    "ANALYSIS_TIMEFRAMES",
    "HIGHER_TIMEFRAMES",
    "MIN_ALIGNMENT_TIMEFRAMES",
    "MIN_USABLE_CANDLES",
    "MarketIntelligenceEngine",
    "MarketIntelligenceInput",
    "MarketIntelligenceReport",
    "TimeframeSeriesInput",
]
