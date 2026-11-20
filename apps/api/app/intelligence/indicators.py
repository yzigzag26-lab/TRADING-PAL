"""Deterministic technical-indicator calculations for Gate 4.

All calculations are pure Python and operate only on caller-supplied closed
candle series. No future candle is ever read: every series function returns a
value aligned to the candle index that produced it, and callers consume only
the final (latest closed) element.

Numerical policy: indicator math uses binary floating point, which is the
standard convention for technical indicators. Prices entering the calculations
are exact ``Decimal`` values converted once to ``float``; outputs are rounded
to 10 significant decimals for stable, reproducible serialisation. This is a
calculation convenience, not a claim of decimal-exact arithmetic — documented
in the Gate 4 methodology notes.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime

from app.intelligence.schemas import IndicatorReading
from app.market_data.candles import HistoricalCandle

# Versioned indicator parameters (Gate 4 methodology v1).
SMA_PERIODS: tuple[int, ...] = (20, 50)
EMA_PERIODS: tuple[int, ...] = (20, 50)
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
ATR_PERIOD = 14
BOLLINGER_PERIOD = 20
BOLLINGER_STD_DEVIATIONS = 2.0
ADX_PERIOD = 14
VOLUME_SMA_PERIOD = 20

_OUTPUT_DIGITS = 10


def _clean(value: float) -> float:
    """Round for stable output; avoid negative zero."""
    rounded = round(value, _OUTPUT_DIGITS)
    return 0.0 if rounded == 0 else rounded


def _sma_series(values: Sequence[float], period: int) -> list[float | None]:
    """Simple moving average; first value appears at index ``period - 1``."""
    out: list[float | None] = [None] * len(values)
    if period < 1 or len(values) < period:
        return out
    window = sum(values[:period])
    out[period - 1] = window / period
    for index in range(period, len(values)):
        window += values[index] - values[index - period]
        out[index] = window / period
    return out


def _ema_series(values: Sequence[float], period: int) -> list[float | None]:
    """EMA seeded by the SMA of the first ``period`` values.

    The seed means early EMA values carry SMA influence; consumers must treat
    ``period`` as the minimum warm-up, not full convergence.
    """
    out: list[float | None] = [None] * len(values)
    if period < 1 or len(values) < period:
        return out
    seed = sum(values[:period]) / period
    multiplier = 2.0 / (period + 1)
    previous = seed
    out[period - 1] = previous
    for index in range(period, len(values)):
        previous = values[index] * multiplier + previous * (1.0 - multiplier)
        out[index] = previous
    return out


def _wilder_smooth(values: Sequence[float], period: int) -> list[float | None]:
    """Wilder smoothing: seed with the mean of the first ``period`` values."""
    out: list[float | None] = [None] * len(values)
    if period < 1 or len(values) < period:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    for index in range(period, len(values)):
        out[index] = (out[index - 1] * (period - 1) + values[index]) / period  # type: ignore[operator]
    return out


def _rsi_series(closes: Sequence[float], period: int) -> list[float | None]:
    """Wilder RSI; requires ``period + 1`` closes for the first value."""
    out: list[float | None] = [None] * len(closes)
    if len(closes) < period + 1:
        return out
    gains: list[float] = []
    losses: list[float] = []
    for index in range(1, len(closes)):
        change = closes[index] - closes[index - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out[period] = _rsi_value(avg_gain, avg_loss)
    for index in range(period + 1, len(closes)):
        avg_gain = (avg_gain * (period - 1) + gains[index - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[index - 1]) / period
        out[index] = _rsi_value(avg_gain, avg_loss)
    return out


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0.0:
        # A perfectly flat series has neither gains nor losses: neutral RSI.
        return 50.0 if avg_gain == 0.0 else 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def _true_ranges(candles: Sequence[HistoricalCandle]) -> list[float]:
    """True range per candle; index 0 has no previous close and is excluded."""
    ranges: list[float] = []
    for index in range(1, len(candles)):
        high = float(candles[index].high)
        low = float(candles[index].low)
        previous_close = float(candles[index - 1].close)
        ranges.append(
            max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )
        )
    return ranges


def _atr_series(candles: Sequence[HistoricalCandle], period: int) -> list[float | None]:
    """Wilder ATR aligned so ``out[i]`` corresponds to ``candles[i]``."""
    out: list[float | None] = [None] * len(candles)
    ranges = _true_ranges(candles)
    if len(ranges) < period:
        return out
    smoothed = _wilder_smooth(ranges, period)
    for offset, value in enumerate(smoothed):
        if value is not None:
            # ranges[k] is the true range of candles[k + 1].
            out[offset + 1] = value
    return out


def _macd_series(
    closes: Sequence[float],
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """MACD line, signal line and histogram aligned to ``closes``."""
    fast = _ema_series(closes, MACD_FAST)
    slow = _ema_series(closes, MACD_SLOW)
    macd_line: list[float | None] = [
        f - s if f is not None and s is not None else None for f, s in zip(fast, slow, strict=True)
    ]
    # Signal is the EMA of the MACD line over defined values only; seed once the
    # slow EMA exists so warm-up stays deterministic.
    defined = [value if value is not None else math.nan for value in macd_line]
    signal = _ema_series_with_nan(defined, MACD_SIGNAL)
    histogram: list[float | None] = [
        m - s if m is not None and s is not None else None
        for m, s in zip(macd_line, signal, strict=True)
    ]
    return macd_line, signal, histogram


def _ema_series_with_nan(values: Sequence[float], period: int) -> list[float | None]:
    """EMA over a series that may contain NaN warm-up slots.

    Only contiguous defined values participate; the first defined run of
    ``period`` values seeds the average, matching the EMA convention used for
    price series.
    """
    out: list[float | None] = [None] * len(values)
    defined_indexes = [index for index, value in enumerate(values) if not math.isnan(value)]
    if len(defined_indexes) < period:
        return out
    seed_values = [values[index] for index in defined_indexes[:period]]
    multiplier = 2.0 / (period + 1)
    previous = sum(seed_values) / period
    seeded_at = defined_indexes[period - 1]
    out[seeded_at] = previous
    for index in defined_indexes[period:]:
        previous = values[index] * multiplier + previous * (1.0 - multiplier)
        out[index] = previous
    return out


def _bollinger_series(
    closes: Sequence[float], period: int, deviations: float
) -> list[tuple[float, float, float, float] | None]:
    """(upper, middle, lower, width) per index; width = (upper-lower)/middle."""
    out: list[tuple[float, float, float, float] | None] = [None] * len(closes)
    for index in range(period - 1, len(closes)):
        window = closes[index - period + 1 : index + 1]
        middle = sum(window) / period
        variance = sum((value - middle) ** 2 for value in window) / period
        sigma = math.sqrt(variance)
        upper = middle + deviations * sigma
        lower = middle - deviations * sigma
        width = (upper - lower) / middle if middle else 0.0
        out[index] = (upper, middle, lower, width)
    return out


def _adx_series(
    candles: Sequence[HistoricalCandle], period: int
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Wilder ADX, +DI and -DI aligned to ``candles``."""
    count = len(candles)
    plus_di: list[float | None] = [None] * count
    minus_di: list[float | None] = [None] * count
    adx: list[float | None] = [None] * count
    if count < 2 * period + 2:
        return plus_di, minus_di, adx

    plus_dm: list[float] = []
    minus_dm: list[float] = []
    true_ranges: list[float] = []
    for index in range(1, count):
        up_move = float(candles[index].high) - float(candles[index - 1].high)
        down_move = float(candles[index - 1].low) - float(candles[index].low)
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
        high = float(candles[index].high)
        low = float(candles[index].low)
        previous_close = float(candles[index - 1].close)
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))

    # Wilder smoothing seeds on the first `period` range entries (indexes 1..period).
    tr_smooth = _wilder_smooth(true_ranges, period)
    pdm_smooth = _wilder_smooth(plus_dm, period)
    mdm_smooth = _wilder_smooth(minus_dm, period)
    dx_values: list[float | None] = [None] * len(true_ranges)
    for index, (tr, pdm, mdm) in enumerate(
        zip(tr_smooth, pdm_smooth, mdm_smooth, strict=True), start=1
    ):
        if tr is None or pdm is None or mdm is None or tr == 0.0:
            continue
        plus_di[index] = 100.0 * pdm / tr
        minus_di[index] = 100.0 * mdm / tr
        di_sum = plus_di[index] + minus_di[index]  # type: ignore[operator]
        if di_sum == 0.0:
            dx_values[index - 1] = 0.0
        else:
            dx_values[index - 1] = (
                100.0 * abs(plus_di[index] - minus_di[index]) / di_sum  # type: ignore[operator]
            )

    # ADX is the Wilder-smoothed mean of DX once `period` DX values exist.
    dx_defined = [value for value in dx_values if value is not None]
    if len(dx_defined) >= period:
        previous = sum(dx_defined[:period]) / period
        # Map the first ADX value to the candle index of the period-th DX entry.
        first_dx_index = next(index for index, value in enumerate(dx_values) if value is not None)
        adx_position = first_dx_index + period - 1
        if adx_position < count:
            adx[adx_position] = previous
            dx_cursor = period
            candle_cursor = adx_position + 1
            while dx_cursor < len(dx_defined) and candle_cursor < count:
                previous = (previous * (period - 1) + dx_defined[dx_cursor]) / period
                adx[candle_cursor] = previous
                dx_cursor += 1
                candle_cursor += 1
    return plus_di, minus_di, adx


def _percentile_rank(values: Sequence[float], latest: float) -> float | None:
    """Fraction of history values at or below ``latest`` (0..1)."""
    if not values:
        return None
    return sum(1 for value in values if value <= latest) / len(values)


def _latest(series: Sequence[float | None]) -> float | None:
    for value in reversed(series):
        if value is not None:
            return value
    return None


def _reading(
    name: str,
    parameters: dict[str, int | float],
    values: dict[str, float | None],
    candle_count: int,
    warmup: int,
    latest_open: datetime,
    calculated_at: datetime,
) -> IndicatorReading:
    defined = {key: _clean(value) for key, value in values.items() if value is not None}
    sufficient = candle_count >= warmup and bool(defined)
    return IndicatorReading(
        name=name,
        parameters=parameters,
        values={key: float(value) for key, value in defined.items()},
        candle_count=candle_count,
        warmup_candles=warmup,
        sufficient_history=sufficient,
        latest_input_open_time=latest_open if sufficient else None,
        calculated_at=calculated_at,
    )


def compute_indicator_readings(
    candles: Sequence[HistoricalCandle],
    *,
    calculated_at: datetime,
) -> tuple[IndicatorReading, ...]:
    """Compute the Gate 4 indicator set on a closed-candle series.

    ``candles`` must already be validated, chronological and closed. The
    function never inspects candle ``is_closed`` itself; the caller owns that
    boundary so forming-candle readings cannot leak into confirmed analysis.
    """
    if not candles:
        return ()
    closes = [float(candle.close) for candle in candles]
    volumes = [float(candle.base_volume) for candle in candles]
    latest_open = candles[-1].open_time
    count = len(candles)
    readings: list[IndicatorReading] = []

    for period in SMA_PERIODS:
        series = _sma_series(closes, period)
        readings.append(
            _reading(
                "SMA",
                {"period": period},
                {"value": _latest(series)},
                count,
                period,
                latest_open,
                calculated_at,
            )
        )

    for period in EMA_PERIODS:
        series = _ema_series(closes, period)
        readings.append(
            _reading(
                "EMA",
                {"period": period},
                {"value": _latest(series)},
                count,
                period,
                latest_open,
                calculated_at,
            )
        )

    rsi = _latest(_rsi_series(closes, RSI_PERIOD))
    readings.append(
        _reading(
            "RSI",
            {"period": RSI_PERIOD},
            {"value": rsi},
            count,
            RSI_PERIOD + 1,
            latest_open,
            calculated_at,
        )
    )

    macd_line, signal_line, histogram = _macd_series(closes)
    readings.append(
        _reading(
            "MACD",
            {"fast": MACD_FAST, "slow": MACD_SLOW, "signal": MACD_SIGNAL},
            {
                "macd": _latest(macd_line),
                "signal": _latest(signal_line),
                "histogram": _latest(histogram),
            },
            count,
            MACD_SLOW + MACD_SIGNAL,
            latest_open,
            calculated_at,
        )
    )

    atr_series = _atr_series(candles, ATR_PERIOD)
    atr = _latest(atr_series)
    atr_percent = _clean(atr / closes[-1] * 100.0) if atr is not None and closes[-1] else None
    readings.append(
        _reading(
            "ATR",
            {"period": ATR_PERIOD},
            {"value": atr, "percent": atr_percent},
            count,
            ATR_PERIOD + 1,
            latest_open,
            calculated_at,
        )
    )

    bollinger = _bollinger_series(closes, BOLLINGER_PERIOD, BOLLINGER_STD_DEVIATIONS)
    latest_bb = bollinger[-1] if bollinger else None
    widths = [entry[3] for entry in bollinger if entry is not None]
    bb_width_percentile = _percentile_rank(widths, latest_bb[3]) if latest_bb is not None else None
    if latest_bb is not None:
        upper, middle, lower, width = latest_bb
        percent_b = (closes[-1] - lower) / (upper - lower) if upper != lower else None
        bb_values: dict[str, float | None] = {
            "upper": upper,
            "middle": middle,
            "lower": lower,
            "width": width,
            "width_percentile": bb_width_percentile,
            "percent_b": percent_b,
        }
    else:
        bb_values = {"width_percentile": bb_width_percentile}
    readings.append(
        _reading(
            "BOLLINGER",
            {"period": BOLLINGER_PERIOD, "deviations": BOLLINGER_STD_DEVIATIONS},
            bb_values,
            count,
            BOLLINGER_PERIOD,
            latest_open,
            calculated_at,
        )
    )

    plus_di, minus_di, adx_series = _adx_series(candles, ADX_PERIOD)
    readings.append(
        _reading(
            "ADX",
            {"period": ADX_PERIOD},
            {
                "adx": _latest(adx_series),
                "plus_di": _latest(plus_di),
                "minus_di": _latest(minus_di),
            },
            count,
            2 * ADX_PERIOD + 2,
            latest_open,
            calculated_at,
        )
    )

    volume_sma_series = _sma_series(volumes, VOLUME_SMA_PERIOD)
    volume_sma = _latest(volume_sma_series)
    relative_volume = _clean(volumes[-1] / volume_sma) if volume_sma else None
    readings.append(
        _reading(
            "VOLUME",
            {"sma_period": VOLUME_SMA_PERIOD},
            {"sma": volume_sma, "relative": relative_volume},
            count,
            VOLUME_SMA_PERIOD,
            latest_open,
            calculated_at,
        )
    )

    return tuple(readings)


def indicator_value(
    readings: Sequence[IndicatorReading], name: str, parameter: str, parameter_value: int
) -> float | None:
    """Return the primary ``value``/first numeric reading for an indicator."""
    for reading in readings:
        if reading.name == name and reading.parameters.get(parameter) == parameter_value:
            if not reading.sufficient_history:
                return None
            for key in ("value", "adx", "macd", "histogram", "relative", "percent_b"):
                if key in reading.values:
                    return reading.values[key]
            return next(iter(reading.values.values()), None)
    return None


__all__ = [
    "ADX_PERIOD",
    "ATR_PERIOD",
    "BOLLINGER_PERIOD",
    "BOLLINGER_STD_DEVIATIONS",
    "EMA_PERIODS",
    "MACD_FAST",
    "MACD_SIGNAL",
    "MACD_SLOW",
    "RSI_PERIOD",
    "SMA_PERIODS",
    "VOLUME_SMA_PERIOD",
    "compute_indicator_readings",
    "indicator_value",
]
