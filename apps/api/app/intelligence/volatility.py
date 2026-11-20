"""Deterministic volatility classification.

Methodology (Gate 4 v1, thresholds versioned here):

- ``atr_percent`` = ATR(14) / latest close * 100.
- ``bollinger_width`` = (upper - lower) / middle of Bollinger(20, 2).
- Each metric's percentile rank is computed against its own trailing history
  (all computed values in the supplied closed series, capped at
  ``HISTORY_LIMIT``).
- ``level``: mean percentile <= ``LOW_PERCENTILE`` → low; >= ``HIGH_PERCENTILE``
  → high; otherwise normal. When only one metric is available it decides alone.
- ``direction``: latest ATR% vs the value ``DIRECTION_LOOKBACK`` candles
  earlier; ratio >= ``EXPANDING_RATIO`` → expanding, <= ``CONTRACTING_RATIO``
  → contracting, else stable. Bollinger width trend is used as a secondary
  confirmation recorded in evidence.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.intelligence.indicators import (
    ATR_PERIOD,
    BOLLINGER_PERIOD,
    BOLLINGER_STD_DEVIATIONS,
    _atr_series,
    _bollinger_series,
    _percentile_rank,
)
from app.intelligence.schemas import (
    IndicatorReading,
    VolatilityAssessment,
    VolatilityDirection,
    VolatilityLevel,
)
from app.market_data.candles import HistoricalCandle

LOW_PERCENTILE = 0.35
HIGH_PERCENTILE = 0.65
DIRECTION_LOOKBACK = 14
EXPANDING_RATIO = 1.15
CONTRACTING_RATIO = 0.87
HISTORY_LIMIT = 200


def assess_volatility(
    candles: Sequence[HistoricalCandle],
    readings: Sequence[IndicatorReading],
) -> VolatilityAssessment:
    """Classify volatility level and direction from deterministic series."""
    evidence: list[str] = []
    atr_values = _atr_series(candles, ATR_PERIOD)
    atr_percent_series: list[float] = []
    for index, atr in enumerate(atr_values):
        if atr is None:
            continue
        close = float(candles[index].close)
        if close > 0:
            atr_percent_series.append(atr / close * 100.0)
    history = atr_percent_series[-HISTORY_LIMIT:]
    atr_percent = history[-1] if history else None
    atr_percentile = _percentile_rank(history, atr_percent) if atr_percent is not None else None

    closes = [float(candle.close) for candle in candles]
    bollinger = _bollinger_series(closes, BOLLINGER_PERIOD, BOLLINGER_STD_DEVIATIONS)
    width_series = [entry[3] for entry in bollinger if entry is not None]
    width_history = width_series[-HISTORY_LIMIT:]
    bb_width = width_history[-1] if width_history else None
    bb_percentile = _percentile_rank(width_history, bb_width) if bb_width is not None else None

    for reading in readings:
        if reading.name == "ATR" and reading.sufficient_history:
            value = reading.values.get("percent")
            if value is not None and atr_percent is None:
                atr_percent = value
        if reading.name == "BOLLINGER" and reading.sufficient_history:
            value = reading.values.get("width")
            if value is not None and bb_width is None:
                bb_width = value * 100.0

    percentiles = [p for p in (atr_percentile, bb_percentile) if p is not None]
    if not percentiles:
        return VolatilityAssessment(
            level="normal",
            direction="stable",
            evidence=("Insufficient history for volatility classification",),
        )
    mean_percentile = sum(percentiles) / len(percentiles)
    level: VolatilityLevel
    if mean_percentile <= LOW_PERCENTILE:
        level = "low"
    elif mean_percentile >= HIGH_PERCENTILE:
        level = "high"
    else:
        level = "normal"
    evidence.append(
        f"Volatility percentile {mean_percentile:.2f} "
        f"(ATR% {atr_percentile if atr_percentile is None else round(atr_percentile, 2)}, "
        f"BB width {bb_percentile if bb_percentile is None else round(bb_percentile, 2)})"
    )

    direction: VolatilityDirection = "stable"
    if len(atr_percent_series) > DIRECTION_LOOKBACK:
        past = atr_percent_series[-(DIRECTION_LOOKBACK + 1)]
        latest = atr_percent_series[-1]
        if past > 0:
            ratio = latest / past
            if ratio >= EXPANDING_RATIO:
                direction = "expanding"
            elif ratio <= CONTRACTING_RATIO:
                direction = "contracting"
            evidence.append(
                f"ATR% changed {((ratio - 1.0) * 100):+.1f}% over {DIRECTION_LOOKBACK} candles"
            )
    if direction == "stable" and len(width_series) > DIRECTION_LOOKBACK:
        past_width = width_series[-(DIRECTION_LOOKBACK + 1)]
        latest_width = width_series[-1]
        if past_width > 0:
            width_ratio = latest_width / past_width
            if width_ratio >= EXPANDING_RATIO:
                direction = "expanding"
                evidence.append("Bollinger width expanding over lookback")
            elif width_ratio <= CONTRACTING_RATIO:
                direction = "contracting"
                evidence.append("Bollinger width contracting over lookback")

    return VolatilityAssessment(
        level=level,
        direction=direction,
        atr=round(atr_values[-1], 10) if atr_values and atr_values[-1] is not None else None,
        atr_percent=round(atr_percent, 6) if atr_percent is not None else None,
        bollinger_width=round(bb_width, 6) if bb_width is not None else None,
        bollinger_width_percentile=(round(bb_percentile, 4) if bb_percentile is not None else None),
        evidence=tuple(evidence),
    )


__all__ = [
    "CONTRACTING_RATIO",
    "DIRECTION_LOOKBACK",
    "EXPANDING_RATIO",
    "HISTORY_LIMIT",
    "HIGH_PERCENTILE",
    "LOW_PERCENTILE",
    "assess_volatility",
]
