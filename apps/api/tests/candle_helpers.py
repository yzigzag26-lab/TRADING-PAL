"""Shared deterministic candle/series fixture builders for Gate 4 tests.

These helpers produce clearly synthetic test fixtures only; they are never
used by production market-data services.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.market_data.candles import (
    BinanceInterval,
    HistoricalCandle,
    HistoricalCandleSeries,
    interval_close_time,
)

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def make_candle(
    open_time: datetime,
    interval: BinanceInterval,
    open_: float,
    high: float,
    low: float,
    close: float,
    *,
    symbol: str = "BTCUSDT",
    volume: float = 100.0,
    is_closed: bool = True,
) -> HistoricalCandle:
    """Build one valid synthetic OHLCV candle for tests."""
    return HistoricalCandle(
        symbol=symbol,
        interval=interval,
        open_time=open_time,
        close_time=interval_close_time(open_time, interval),
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        base_volume=Decimal(str(volume)),
        quote_volume=Decimal(str(volume * close)),
        trade_count=10,
        taker_buy_base_volume=Decimal(str(volume / 2)),
        taker_buy_quote_volume=Decimal(str(volume * close / 2)),
        received_time=open_time + timedelta(seconds=30),
        is_closed=is_closed,
    )


_INTERVAL_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
}


def candle_series(
    count: int,
    interval: BinanceInterval,
    prices: list[tuple[float, float, float, float]] | None = None,
    *,
    start: datetime = BASE_TIME,
    step: timedelta | None = None,
    symbol: str = "BTCUSDT",
    is_closed: bool = True,
) -> list[HistoricalCandle]:
    """Build ``count`` chronological synthetic candles.

    ``prices`` supplies explicit (open, high, low, close) tuples; otherwise a
    gentle deterministic oscillation around 100 is generated. ``step`` defaults
    to the interval length so open times stay boundary-aligned.
    """
    if step is None:
        step = timedelta(seconds=_INTERVAL_SECONDS[interval])
    candles: list[HistoricalCandle] = []
    for index in range(count):
        open_time = start + index * step
        if prices is not None:
            o, h, low, c = prices[index]
        else:
            base = 100.0 + (index % 10) * 0.5
            o, c = base, base + 0.4
            h, low = base + 0.8, base - 0.2
        candles.append(
            make_candle(open_time, interval, o, h, low, c, symbol=symbol, is_closed=is_closed)
        )
    return candles


def make_series(
    candles: list[HistoricalCandle],
    *,
    interval: BinanceInterval = "1h",
    symbol: str = "BTCUSDT",
    missing_open_times: tuple[datetime, ...] = (),
) -> HistoricalCandleSeries:
    """Wrap candles in a validated HistoricalCandleSeries."""
    missing = tuple(sorted(set(missing_open_times)))
    if candles:
        requested_start = candles[0].open_time
        requested_end = candles[-1].open_time
    else:
        requested_start = requested_end = BASE_TIME
    return HistoricalCandleSeries(
        symbol=symbol,
        interval=interval,
        requested_start=requested_start,
        requested_end=requested_end,
        candles=tuple(candles),
        missing_open_times=missing,
        complete=not missing,
        recovery_attempts=0,
    )
