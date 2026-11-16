"""Validated Binance Spot OHLCV candle domain models and interval arithmetic."""

from __future__ import annotations

import calendar
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

BinanceInterval = Literal[
    "1s", "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h",
    "6h", "8h", "12h", "1d", "3d", "1w", "1M",
]
INTERVALS: tuple[str, ...] = (
    "1s", "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h",
    "6h", "8h", "12h", "1d", "3d", "1w", "1M",
)


def parse_utc_milliseconds(value: int) -> datetime:
    """Convert Binance millisecond epoch timestamps to aware UTC datetimes."""
    return datetime.fromtimestamp(value / 1000, tz=UTC)


def interval_next_open(open_time: datetime, interval: str) -> datetime:
    """Return the next Binance candle open boundary for a supported interval."""
    if interval not in INTERVALS:
        raise ValueError("Unsupported Binance kline interval")
    if interval.endswith("M"):
        month_index = open_time.year * 12 + open_time.month
        year, month_zero = divmod(month_index, 12)
        month = month_zero + 1
        return open_time.replace(
            year=year, month=month, day=1, hour=0, minute=0,
            second=0, microsecond=0,
        )
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    amount = int(interval[:-1]) * units[interval[-1]]
    from datetime import timedelta
    return open_time + timedelta(seconds=amount)


def is_interval_boundary(value: datetime, interval: str) -> bool:
    """Return whether a UTC timestamp is aligned to a Binance interval open."""
    if interval not in INTERVALS or value.tzinfo is None or value.utcoffset() is None:
        return False
    value = value.astimezone(UTC)
    if interval.endswith("M"):
        return value.day == 1 and value.hour == value.minute == value.second == value.microsecond == 0
    if interval == "1w":
        return value.weekday() == 0 and value.hour == value.minute == value.second == value.microsecond == 0
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    seconds = int(interval[:-1]) * units[interval[-1]]
    epoch_seconds = int(value.timestamp())
    return value.microsecond == 0 and epoch_seconds % seconds == 0


def interval_close_time(open_time: datetime, interval: str) -> datetime:
    """Return Binance's inclusive close timestamp (one millisecond before next open)."""
    from datetime import timedelta
    return interval_next_open(open_time, interval) - timedelta(milliseconds=1)


def expected_open_times(start: datetime, end: datetime, interval: str) -> list[datetime]:
    """Enumerate candle open times in the half-open [start, end] query boundary."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("Historical range timestamps must be timezone-aware")
    if start > end:
        raise ValueError("Historical range start must not be after end")
    current = start.astimezone(UTC)
    final = end.astimezone(UTC)
    if not is_interval_boundary(current, interval) or not is_interval_boundary(final, interval):
        raise ValueError("Historical range boundaries must align to the requested interval")
    values: list[datetime] = []
    while current <= final:
        values.append(current)
        following = interval_next_open(current, interval)
        if following <= current:
            raise ValueError("Interval arithmetic did not advance")
        current = following
    return values


class HistoricalCandle(BaseModel):
    """A single validated Binance Spot kline with full OHLCV provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    exchange: Literal["BINANCE"] = "BINANCE"
    market: Literal["SPOT"] = "SPOT"
    symbol: str = Field(min_length=1, max_length=30)
    interval: BinanceInterval
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    base_volume: Decimal
    quote_volume: Decimal
    trade_count: int = Field(ge=0)
    taker_buy_base_volume: Decimal
    taker_buy_quote_volume: Decimal
    received_time: datetime
    is_closed: bool

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized.isalnum():
            raise ValueError("symbol must contain only letters and digits")
        return normalized

    @field_validator(
        "open", "high", "low", "close", "base_volume", "quote_volume",
        "taker_buy_base_volume", "taker_buy_quote_volume", mode="before",
    )
    @classmethod
    def parse_decimal(cls, value: object) -> Decimal:
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("OHLCV fields must be valid decimals") from exc
        if not parsed.is_finite():
            raise ValueError("OHLCV fields must be finite")
        return parsed

    @field_validator("open_time", "close_time", "received_time")
    @classmethod
    def require_aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Candle timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_ohlcv(self) -> HistoricalCandle:
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC prices must be greater than zero")
        if self.low > min(self.open, self.close):
            raise ValueError("Candle low cannot exceed open or close")
        if self.high < max(self.open, self.close):
            raise ValueError("Candle high cannot be below open or close")
        if self.low > self.high:
            raise ValueError("Candle low cannot exceed high")
        if min(
            self.base_volume, self.quote_volume,
            self.taker_buy_base_volume, self.taker_buy_quote_volume,
        ) < 0:
            raise ValueError("Candle volumes cannot be negative")
        if self.taker_buy_base_volume > self.base_volume:
            raise ValueError("Taker-buy base volume cannot exceed total base volume")
        if self.taker_buy_quote_volume > self.quote_volume:
            raise ValueError("Taker-buy quote volume cannot exceed total quote volume")
        if self.close_time != interval_close_time(self.open_time, self.interval):
            raise ValueError("Candle close time does not match its interval")
        if self.open_time > self.close_time:
            raise ValueError("Candle open time must not be after close time")
        return self


class HistoricalCandleSeries(BaseModel):
    """A historical candle response with explicit continuity/recovery status."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    interval: BinanceInterval
    requested_start: datetime
    requested_end: datetime
    candles: tuple[HistoricalCandle, ...]
    missing_open_times: tuple[datetime, ...]
    complete: bool
    recovery_attempts: int = Field(ge=0)
    source: Literal["binance_spot_rest"] = "binance_spot_rest"

    @model_validator(mode="after")
    def validate_series_integrity(self) -> HistoricalCandleSeries:
        if self.requested_start.tzinfo is None or self.requested_end.tzinfo is None:
            raise ValueError("Historical series range must be timezone-aware")
        if self.requested_start > self.requested_end:
            raise ValueError("Historical series start must not be after end")
        opens = [candle.open_time for candle in self.candles]
        if opens != sorted(set(opens)):
            raise ValueError("Historical candles must be unique and chronological")
        if any(
            candle.symbol != self.symbol or candle.interval != self.interval
            for candle in self.candles
        ):
            raise ValueError("Historical series contains a mismatched candle")
        if self.complete != (len(self.missing_open_times) == 0):
            raise ValueError("Historical completeness flag does not match missing intervals")
        if tuple(sorted(set(self.missing_open_times))) != self.missing_open_times:
            raise ValueError("Missing candle timestamps must be unique and chronological")
        return self
