"""Deterministic trend classification from verified indicator readings."""

from __future__ import annotations

from collections.abc import Sequence

from app.intelligence.indicators import indicator_value
from app.intelligence.schemas import (
    IndicatorReading,
    TrendAssessment,
    TrendDirection,
)
from app.market_data.candles import HistoricalCandle

# Versioned Gate 4 trend methodology.
BULLISH_THRESHOLD = 0.35
BEARISH_THRESHOLD = -0.35
ADX_TRENDING_LEVEL = 20.0
ADX_STRONG_LEVEL = 25.0
MOMENTUM_LOOKBACK = 20
SLOPE_BULLISH = 0.005
SLOPE_BEARISH = -0.005


def _slope(closes: Sequence[float]) -> float | None:
    """Simple endpoint slope over the momentum window, relative to price."""
    if len(closes) < MOMENTUM_LOOKBACK + 1:
        return None
    window = closes[-(MOMENTUM_LOOKBACK + 1) :]
    start = window[0]
    if start == 0:
        return None
    return (window[-1] - start) / start


def classify_trend(
    candles: Sequence[HistoricalCandle],
    readings: Sequence[IndicatorReading],
) -> TrendAssessment:
    """Classify trend from multiple evidence sources; never one indicator alone."""
    if len(candles) < 2:
        return TrendAssessment(
            direction="uncertain",
            score=0.0,
            evidence=("Insufficient candle history for trend classification",),
        )

    close = float(candles[-1].close)
    closes = [float(candle.close) for candle in candles]
    evidence: list[str] = []
    conflicts: list[str] = []
    votes: list[tuple[float, float]] = []

    def vote(value: float | None, weight: float, label: str) -> None:
        if value is None:
            conflicts.append(f"{label} unavailable (insufficient history)")
            return
        votes.append((value, weight))

    ema20 = indicator_value(readings, "EMA", "period", 20)
    ema50 = indicator_value(readings, "EMA", "period", 50)
    sma20 = indicator_value(readings, "SMA", "period", 20)
    sma50 = indicator_value(readings, "SMA", "period", 50)
    rsi = indicator_value(readings, "RSI", "period", 14)
    macd_hist = None
    for reading in readings:
        if reading.name == "MACD" and reading.sufficient_history:
            macd_hist = reading.values.get("histogram")
    adx = indicator_value(readings, "ADX", "period", 14)
    plus_di = None
    minus_di = None
    for reading in readings:
        if reading.name == "ADX" and reading.sufficient_history:
            plus_di = reading.values.get("plus_di")
            minus_di = reading.values.get("minus_di")

    if ema20 is not None:
        delta = close - ema20
        direction = 1.0 if delta > 0 else -1.0 if delta < 0 else 0.0
        vote(direction, 0.15, f"close vs EMA20 ({'above' if delta > 0 else 'below'})")
        evidence.append(
            f"Close {close:.6g} is {'above' if delta > 0 else 'below'} EMA20 {ema20:.6g}"
        )
    if ema50 is not None and ema20 is not None:
        if ema20 == ema50:
            vote(0.0, 0.05, "EMA20 equals EMA50")
            evidence.append("EMA20 equals EMA50 (neutral)")
        else:
            direction = 1.0 if ema20 > ema50 else -1.0
            vote(direction, 0.20, "EMA20 vs EMA50")
            evidence.append(f"EMA20 {'above' if ema20 > ema50 else 'below'} EMA50")
    if sma20 is not None and sma50 is not None:
        if sma20 == sma50:
            vote(0.0, 0.03, "SMA20 equals SMA50")
            evidence.append("SMA20 equals SMA50 (neutral)")
        else:
            direction = 1.0 if sma20 > sma50 else -1.0
            vote(direction, 0.10, "SMA20 vs SMA50")
            evidence.append(f"SMA20 {'above' if sma20 > sma50 else 'below'} SMA50")
    if rsi is not None:
        if rsi > 55:
            vote(1.0, 0.10, "RSI momentum")
        elif rsi < 45:
            vote(-1.0, 0.10, "RSI momentum")
        else:
            vote(0.0, 0.05, "RSI neutral")
        evidence.append(f"RSI14 {rsi:.2f}")
    if macd_hist is not None:
        direction = 1.0 if macd_hist > 0 else -1.0 if macd_hist < 0 else 0.0
        vote(direction, 0.10, "MACD histogram")
        evidence.append(f"MACD histogram {'positive' if macd_hist > 0 else 'negative'}")
    if adx is not None:
        if adx >= ADX_TRENDING_LEVEL and plus_di is not None and minus_di is not None:
            direction = 1.0 if plus_di > minus_di else -1.0
            vote(direction, 0.15, "ADX directional movement")
            evidence.append(
                f"ADX14 {adx:.1f} with {'+DI' if plus_di > minus_di else '-DI'} dominant"
            )
        elif adx < ADX_TRENDING_LEVEL:
            vote(0.0, 0.05, "ADX weak trend")
            evidence.append(f"ADX14 {adx:.1f} indicates no strong trend")
        else:
            conflicts.append("ADX available but directional indexes missing")
    slope = _slope(closes)
    if slope is not None:
        if slope >= SLOPE_BULLISH:
            vote(1.0, 0.10, "price slope")
        elif slope <= SLOPE_BEARISH:
            vote(-1.0, 0.10, "price slope")
        else:
            vote(0.0, 0.05, "flat price slope")
        evidence.append(f"{MOMENTUM_LOOKBACK}-candle slope {slope * 100:.2f}%")

    if not votes:
        return TrendAssessment(
            direction="uncertain",
            score=0.0,
            evidence=tuple(evidence),
            conflicts=tuple(conflicts),
        )

    score = sum(value * weight for value, weight in votes) / sum(weight for _, weight in votes)
    score = max(-1.0, min(1.0, score))

    adx_value = adx if adx is not None else 0.0
    if adx_value < ADX_TRENDING_LEVEL:
        # Weak directional movement suppresses trend conviction.
        score *= 0.6

    final_direction: TrendDirection
    if score >= BULLISH_THRESHOLD:
        final_direction = "bullish"
    elif score <= BEARISH_THRESHOLD:
        final_direction = "bearish"
    elif adx_value < ADX_STRONG_LEVEL:
        final_direction = "ranging"
    else:
        final_direction = "transitioning"

    return TrendAssessment(
        direction=final_direction,
        score=round(score, 4),
        evidence=tuple(evidence),
        conflicts=tuple(conflicts),
    )


__all__ = ["classify_trend"]
