"""Bounded historical candle retrieval, continuity checks and gap recovery."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from app.market_data.binance_historical_rest import MAX_KLINE_LIMIT, BinanceHistoricalRestClient
from app.market_data.candles import (
    HistoricalCandle,
    HistoricalCandleSeries,
    INTERVALS,
    expected_open_times,
    interval_next_open,
)
from app.market_data.freshness import MarketDataUnavailable


class HistoricalKlineClient(Protocol):
    async def klines(
        self,
        symbol: str,
        interval: str,
        *,
        start_time: datetime,
        end_time: datetime,
        limit: int = MAX_KLINE_LIMIT,
        now: datetime | None = None,
    ) -> list[HistoricalCandle]: ...


class BinanceHistoricalCandleService:
    """Retrieve bounded historical ranges and recover missing intervals explicitly."""

    def __init__(
        self,
        *,
        rest_client: HistoricalKlineClient | None = None,
        max_candles: int = 10_000,
        recovery_attempts: int = 2,
    ) -> None:
        if not 1 <= max_candles <= 100_000:
            raise ValueError("max_candles must be between 1 and 100000")
        if not 0 <= recovery_attempts <= 3:
            raise ValueError("recovery_attempts must be between 0 and 3")
        self._rest = rest_client or BinanceHistoricalRestClient()
        self._owns_rest = rest_client is None
        self._max_candles = max_candles
        self._recovery_attempts = recovery_attempts
        self._started = False

    async def start(self) -> None:
        if not self._started:
            if self._owns_rest:
                await self._rest.__aenter__()  # type: ignore[attr-defined]
            self._started = True

    async def close(self) -> None:
        if self._owns_rest and self._started:
            await self._rest.__aexit__(None, None, None)  # type: ignore[attr-defined]
        self._started = False

    async def fetch(
        self,
        symbol: str,
        interval: str,
        *,
        start_time: datetime,
        end_time: datetime,
        now: datetime | None = None,
    ) -> HistoricalCandleSeries:
        """Fetch a range, page at 1000 rows, detect gaps and retry missing ranges."""
        normalized = symbol.strip().upper()
        if not normalized.isalnum() or not 1 <= len(normalized) <= 30:
            raise ValueError("symbol must contain only letters and digits")
        if interval not in INTERVALS:
            raise ValueError("Unsupported Binance kline interval")
        if start_time.tzinfo is None or end_time.tzinfo is None:
            raise ValueError("Historical range timestamps must be timezone-aware")
        start = start_time.astimezone(UTC)
        end = end_time.astimezone(UTC)
        if start > end:
            raise ValueError("Historical range start must not be after end")
        expected = expected_open_times(start, end, interval)
        if not expected:
            raise ValueError("Historical range contains no candle boundaries")
        if len(expected) > self._max_candles:
            raise ValueError(
                f"Requested range exceeds the configured {self._max_candles}-candle limit"
            )
        if not self._started:
            await self.start()

        candles: dict[datetime, HistoricalCandle] = {}
        await self._fetch_range(normalized, interval, start, end, candles, now)
        recovery_count = 0
        missing = self._missing(expected, candles)
        for _ in range(self._recovery_attempts):
            if not missing:
                break
            recovery_count += 1
            ranges = self._missing_ranges(missing, interval)
            for gap_start, gap_end in ranges:
                await self._fetch_range(normalized, interval, gap_start, gap_end, candles, now)
            missing = self._missing(expected, candles)

        ordered = tuple(candles[key] for key in sorted(candles) if key in set(expected))
        return HistoricalCandleSeries(
            symbol=normalized,
            interval=interval,
            requested_start=start,
            requested_end=end,
            candles=ordered,
            missing_open_times=tuple(missing),
            complete=not missing,
            recovery_attempts=recovery_count,
        )

    async def _fetch_range(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
        candles: dict[datetime, HistoricalCandle],
        now: datetime | None,
    ) -> None:
        cursor = start
        while cursor <= end:
            page = await self._rest.klines(
                symbol,
                interval,
                start_time=cursor,
                end_time=end,
                limit=min(MAX_KLINE_LIMIT, self._max_candles),
                now=now,
            )
            if not page:
                return
            for candle in page:
                if candle.symbol != symbol or candle.interval != interval:
                    raise MarketDataUnavailable("Binance returned a mismatched candle series")
                if candle.open_time < cursor or candle.open_time > end:
                    raise MarketDataUnavailable(
                        "Binance returned a candle outside the requested range"
                    )
                existing = candles.get(candle.open_time)
                if existing is not None and existing != candle:
                    raise MarketDataUnavailable("Conflicting candle values found during recovery")
                candles[candle.open_time] = candle
            last_open = page[-1].open_time
            following = interval_next_open(last_open, interval)
            if following <= cursor:
                raise MarketDataUnavailable("Historical pagination did not advance")
            cursor = following
            if len(candles) > self._max_candles:
                raise MarketDataUnavailable(
                    "Historical result exceeded its configured candle limit"
                )
            if len(page) < min(MAX_KLINE_LIMIT, self._max_candles):
                return

    @staticmethod
    def _missing(
        expected: list[datetime],
        candles: dict[datetime, HistoricalCandle],
    ) -> list[datetime]:
        return [open_time for open_time in expected if open_time not in candles]

    @staticmethod
    def _missing_ranges(
        missing: list[datetime],
        interval: str,
    ) -> list[tuple[datetime, datetime]]:
        if not missing:
            return []
        ranges: list[tuple[datetime, datetime]] = []
        first = previous = missing[0]
        for current in missing[1:]:
            if interval_next_open(previous, interval) != current:
                ranges.append((first, previous))
                first = current
            previous = current
        ranges.append((first, previous))
        return ranges
