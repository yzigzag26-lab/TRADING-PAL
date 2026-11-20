"""Deterministic known-value tests for the Gate 4 indicator engine."""

from __future__ import annotations

from datetime import UTC, datetime

from app.intelligence.indicators import (
    compute_indicator_readings,
    indicator_value,
)
from app.intelligence.schemas import IndicatorReading
from tests.candle_helpers import BASE_TIME, candle_series

CALCULATED_AT = datetime(2026, 2, 1, tzinfo=UTC)


def _readings(closes: list[float], interval: str = "1h") -> tuple[IndicatorReading, ...]:
    candles = candle_series(
        len(closes),
        interval,  # type: ignore[arg-type]
        [(c - 0.1, c + 0.2, c - 0.3, c) for c in closes],
        start=BASE_TIME,
    )
    return compute_indicator_readings(candles, calculated_at=CALCULATED_AT)


def test_sma_known_value() -> None:
    closes = [float(i) for i in range(1, 31)]  # 1..30
    readings = _readings(closes)
    sma20 = next(r for r in readings if r.name == "SMA" and r.parameters["period"] == 20)
    assert sma20.sufficient_history
    # Mean of closes 11..30 = 20.5
    assert sma20.values["value"] == 20.5
    sma50 = next(r for r in readings if r.name == "SMA" and r.parameters["period"] == 50)
    assert not sma50.sufficient_history
    assert sma50.values == {}


def test_ema_produces_value_after_warmup() -> None:
    closes = [100.0 + i for i in range(60)]
    readings = _readings(closes)
    ema20 = next(r for r in readings if r.name == "EMA" and r.parameters["period"] == 20)
    assert ema20.sufficient_history
    assert ema20.values["value"] is not None
    assert ema20.values["value"] < closes[-1]  # EMA lags a rising series


def test_rsi_is_100_on_monotonic_rise() -> None:
    readings = _readings([100.0 + i for i in range(30)])
    rsi = next(r for r in readings if r.name == "RSI")
    assert rsi.values["value"] == 100.0


def test_rsi_is_0_on_monotonic_fall() -> None:
    readings = _readings([200.0 - i for i in range(30)])
    rsi = next(r for r in readings if r.name == "RSI")
    assert rsi.values["value"] == 0.0


def test_macd_histogram_positive_in_uptrend() -> None:
    # Accelerating rise: MACD line outruns its signal EMA, histogram > 0.
    readings = _readings([100.0 + 0.3 * i + 0.02 * i * i for i in range(80)])
    macd = next(r for r in readings if r.name == "MACD")
    assert macd.sufficient_history
    assert macd.values["histogram"] is not None
    assert macd.values["histogram"] > 0
    assert macd.values["macd"] is not None
    assert macd.values["signal"] is not None


def test_atr_constant_on_constant_range() -> None:
    # Every candle: open=close=100, high=101, low=99 -> TR = 2 (vs prev close 100)
    candles = candle_series(
        30,
        "1h",
        [(100.0, 101.0, 99.0, 100.0)] * 30,
        start=BASE_TIME,
    )
    readings = compute_indicator_readings(candles, calculated_at=CALCULATED_AT)
    atr = next(r for r in readings if r.name == "ATR")
    assert atr.sufficient_history
    assert atr.values["value"] == 2.0
    assert atr.values["percent"] is not None
    assert abs(atr.values["percent"] - 2.0) < 0.001


def test_bollinger_bands_ordering() -> None:
    readings = _readings([100.0 + (i % 7) for i in range(60)])
    bb = next(r for r in readings if r.name == "BOLLINGER")
    assert bb.sufficient_history
    assert bb.values["upper"] > bb.values["middle"] > bb.values["lower"]
    assert 0.0 <= bb.values["percent_b"] <= 1.0


def test_adx_high_on_strong_trend() -> None:
    # Steady uptrend with small pullbacks produces directional movement.
    closes = []
    price = 100.0
    for i in range(120):
        price += 0.5 if i % 4 else -0.2
        closes.append(price)
    candles = candle_series(
        len(closes),
        "1h",
        [(c - 0.1, c + 0.3, c - 0.4, c) for c in closes],
        start=BASE_TIME,
    )
    readings = compute_indicator_readings(candles, calculated_at=CALCULATED_AT)
    adx = next(r for r in readings if r.name == "ADX")
    assert adx.values.get("adx") is not None
    assert adx.values["adx"] > 25.0
    assert adx.values["plus_di"] > adx.values["minus_di"]


def test_insufficient_history_never_reports_valid() -> None:
    readings = _readings([100.0] * 10)
    for reading in readings:
        if reading.warmup_candles > 10:
            assert not reading.sufficient_history
            assert reading.values == {}
            assert reading.latest_input_open_time is None
    assert indicator_value(readings, "SMA", "period", 50) is None
    assert indicator_value(readings, "RSI", "period", 14) is None


def test_indicator_value_helper() -> None:
    readings = _readings([100.0 + i for i in range(60)])
    assert indicator_value(readings, "RSI", "period", 14) == 100.0
    assert indicator_value(readings, "EMA", "period", 20) is not None
    assert indicator_value(readings, "ADX", "period", 14) is not None


def test_empty_series_returns_no_readings() -> None:
    assert compute_indicator_readings((), calculated_at=CALCULATED_AT) == ()
