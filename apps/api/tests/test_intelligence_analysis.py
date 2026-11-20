"""Deterministic tests for trend, structure, zones, volatility and the analyzer."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.intelligence.analyzer import (
    MarketIntelligenceEngine,
    MarketIntelligenceInput,
    TimeframeSeriesInput,
)
from app.intelligence.structure import analyze_structure, detect_swings
from app.intelligence.trend import classify_trend
from app.intelligence.volatility import assess_volatility
from app.intelligence.zones import derive_zones
from app.market_data.candles import HistoricalCandle
from app.market_data.models import ValidatedPrice
from tests.candle_helpers import BASE_TIME, candle_series, make_series

NOW = datetime(2026, 2, 1, tzinfo=UTC)


def _uptrend(
    count: int = 120, start: float = 100.0, step: float = 0.4, interval: str = "1h"
) -> list[HistoricalCandle]:
    closes = [start + i * step for i in range(count)]
    return candle_series(
        count,
        interval,  # type: ignore[arg-type]
        [(c - 0.1, c + 0.3, c - 0.2, c) for c in closes],
        start=BASE_TIME,
    )


def _downtrend(
    count: int = 120, start: float = 200.0, step: float = -0.4, interval: str = "1h"
) -> list[HistoricalCandle]:
    closes = [start + i * step for i in range(count)]
    return candle_series(
        count,
        interval,  # type: ignore[arg-type]
        [(c + 0.1, c + 0.2, c - 0.3, c) for c in closes],
        start=BASE_TIME,
    )


def _rangebound(count: int = 120, interval: str = "1h") -> list[HistoricalCandle]:
    # Period-4 square wave: zero drift, symmetric so EMAs converge to ~100.
    closes = [100.0 + (0.6 if (i // 2) % 2 == 0 else -0.6) for i in range(count)]
    return candle_series(
        count,
        interval,  # type: ignore[arg-type]
        [(c, c + 0.2, c - 0.2, c) for c in closes],
        start=BASE_TIME,
    )


def _wave(count: int = 160, interval: str = "1h") -> list[HistoricalCandle]:
    """Sine-wave fixture that produces real confirmed swing highs and lows."""
    import math

    closes = [100.0 + 4.0 * math.sin(i / 6.0) for i in range(count)]
    return candle_series(
        count,
        interval,  # type: ignore[arg-type]
        [(c - 0.1, c + 0.3, c - 0.3, c) for c in closes],
        start=BASE_TIME,
    )


def test_detect_swings_requires_confirmation_window() -> None:
    candles = _uptrend(60)
    swings = detect_swings(candles, window=3)
    # Only pivots with 3 confirmed candles on each side are returned.
    assert all(point.confirmed_at_index < len(candles) for point in swings)
    assert len(swings) < len(candles)


def test_structure_finds_sequence_on_trending_series() -> None:
    candles = _uptrend(150)
    findings = analyze_structure(candles)
    kinds = {finding.kind for finding in findings}
    assert kinds, "expected at least one structure finding"
    assert all(finding.confirmed for finding in findings if finding.kind != "consolidation")


def test_structure_reports_insufficient_swings_on_short_series() -> None:
    candles = candle_series(10, "1h", start=BASE_TIME)
    findings = analyze_structure(candles)
    assert len(findings) == 1
    assert findings[0].kind == "consolidation"
    assert not findings[0].confirmed


def test_zones_derive_from_swing_points() -> None:
    candles = _wave(160)
    zones = derive_zones(candles, timeframe="1h", atr_value=1.0)
    assert zones, "expected at least one zone"
    for zone in zones:
        assert zone.lower <= zone.upper
        assert zone.touches >= 1
        assert zone.timeframe == "1h"
        assert zone.method == "swing_cluster_v1"
        assert zone.source_open_times


def test_zones_empty_on_tiny_series() -> None:
    candles = candle_series(8, "1h", start=BASE_TIME)
    assert derive_zones(candles, timeframe="1h", atr_value=None) == ()


def test_trend_classifies_uptrend_as_bullish() -> None:
    candles = _uptrend(150)
    from app.intelligence.indicators import compute_indicator_readings

    readings = compute_indicator_readings(candles, calculated_at=NOW)
    trend = classify_trend(candles, readings)
    assert trend.direction == "bullish"
    assert trend.score > 0
    assert trend.evidence


def test_trend_classifies_downtrend_as_bearish() -> None:
    candles = _downtrend(150)
    from app.intelligence.indicators import compute_indicator_readings

    readings = compute_indicator_readings(candles, calculated_at=NOW)
    trend = classify_trend(candles, readings)
    assert trend.direction == "bearish"
    assert trend.score < 0


def test_trend_classifies_rangebound_market() -> None:
    candles = _rangebound(150)
    from app.intelligence.indicators import compute_indicator_readings

    readings = compute_indicator_readings(candles, calculated_at=NOW)
    trend = classify_trend(candles, readings)
    assert trend.direction in {"ranging", "transitioning", "uncertain"}


def test_volatility_assessment_returns_classification() -> None:
    candles = _uptrend(150)
    from app.intelligence.indicators import compute_indicator_readings

    readings = compute_indicator_readings(candles, calculated_at=NOW)
    vol = assess_volatility(candles, readings)
    assert vol.level in {"low", "normal", "high"}
    assert vol.direction in {"expanding", "contracting", "stable"}


def _bundle(directions: dict[str, str], *, complete: bool = True) -> MarketIntelligenceInput:
    """Build a MarketIntelligenceInput with synthetic per-timeframe series."""
    price = ValidatedPrice(
        exchange="BINANCE",
        market="SPOT",
        symbol="BTCUSDT",
        price=Decimal("100"),
        market_event_timestamp=NOW,
        received_timestamp=NOW,
        validated_timestamp=NOW,
        age_ms_at_validation=0,
        source="binance_spot_rest",
        event_id="t1",
    )
    timeframes = {}
    for interval, direction in directions.items():
        if direction == "bullish":
            candles = _uptrend(120, interval=interval)
        elif direction == "bearish":
            candles = _downtrend(120, interval=interval)
        else:
            candles = _rangebound(120, interval=interval)
        series = make_series(candles, interval=interval)  # type: ignore[arg-type]
        timeframes[interval] = TimeframeSeriesInput(
            interval=interval, series=series, snapshot_id=None
        )
    return MarketIntelligenceInput(price=price, price_snapshot_id=None, timeframes=timeframes)


def test_analyzer_produces_report_for_all_timeframes() -> None:
    bundle = _bundle(
        {"5m": "bullish", "15m": "bullish", "1h": "bullish", "4h": "bullish", "1d": "bullish"}
    )
    report = MarketIntelligenceEngine().analyze(bundle, analyzed_at=NOW)
    assert report.symbol == "BTCUSDT"
    assert len(report.timeframe_analyses) == 5
    assert report.alignment.status == "aligned_bullish"
    assert report.data_quality == "complete"
    assert report.readiness == "ready"


def test_analyzer_marks_conflicting_timeframes() -> None:
    bundle = _bundle(
        {"5m": "bullish", "15m": "bullish", "1h": "bearish", "4h": "bearish", "1d": "bearish"}
    )
    report = MarketIntelligenceEngine().analyze(bundle, analyzed_at=NOW)
    assert report.alignment.status == "conflicting"


def test_analyzer_degrades_when_timeframe_missing() -> None:
    bundle = _bundle({"5m": "bullish", "15m": "bullish", "1h": "bullish"})
    report = MarketIntelligenceEngine().analyze(bundle, analyzed_at=NOW)
    # Three usable timeframes still produce an alignment verdict, but the
    # report is degraded because two required series are absent.
    assert report.alignment.status == "aligned_bullish"
    assert report.data_quality == "partial"
    assert report.readiness == "degraded"
    assert "timeframe:4h" in report.missing_inputs
    assert "timeframe:1d" in report.missing_inputs


def test_analyzer_marks_unusable_short_series() -> None:
    price = ValidatedPrice(
        exchange="BINANCE",
        market="SPOT",
        symbol="BTCUSDT",
        price=Decimal("100"),
        market_event_timestamp=NOW,
        received_timestamp=NOW,
        validated_timestamp=NOW,
        age_ms_at_validation=0,
        source="binance_spot_rest",
        event_id="t1",
    )
    candles = candle_series(20, "1h", start=BASE_TIME)
    series = make_series(candles, interval="1h")
    bundle = MarketIntelligenceInput(
        price=price,
        price_snapshot_id=None,
        timeframes={
            "1h": TimeframeSeriesInput(interval="1h", series=series),
        },
    )
    report = MarketIntelligenceEngine().analyze(bundle, analyzed_at=NOW)
    analysis = report.timeframe_analyses[0]
    assert not analysis.usable
    assert analysis.closed_candle_count == 20


def test_trend_flat_series_is_neutral_not_bearish() -> None:
    """F5: equal moving averages must not be classified as bearish."""
    from app.intelligence.indicators import compute_indicator_readings

    candles = candle_series(150, "1h", [(99.9, 100.1, 99.8, 100.0)] * 150, start=BASE_TIME)
    readings = compute_indicator_readings(candles, calculated_at=NOW)
    trend = classify_trend(candles, readings)
    assert trend.direction in {"ranging", "transitioning", "uncertain"}
    assert any("neutral" in item for item in trend.evidence)
