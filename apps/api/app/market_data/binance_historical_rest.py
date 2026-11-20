"""Public Binance Spot REST adapter for historical klines."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from app.market_data.candles import (
    INTERVALS,
    BinanceInterval,
    HistoricalCandle,
    interval_close_time,
    parse_utc_milliseconds,
)
from app.market_data.freshness import MarketDataUnavailable
from app.market_data.rest_retry import DEFAULT_RETRY_POLICY, RestRetryPolicy, get_with_retry

BINANCE_SPOT_REST_BASE_URL = "https://data-api.binance.vision"
MAX_KLINE_LIMIT = 1_000


class BinanceHistoricalRestClient:
    """Read-only kline client; uses public market data and no API credentials."""

    def __init__(
        self,
        *,
        base_url: str = BINANCE_SPOT_REST_BASE_URL,
        timeout_seconds: float = 8.0,
        client: httpx.AsyncClient | None = None,
        retry_policy: RestRetryPolicy = DEFAULT_RETRY_POLICY,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client
        self._owns_client = client is None
        self._retry_policy = retry_policy

    async def __aenter__(self) -> BinanceHistoricalRestClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def klines(
        self,
        symbol: str,
        interval: BinanceInterval,
        *,
        start_time: datetime,
        end_time: datetime,
        limit: int = MAX_KLINE_LIMIT,
        now: datetime | None = None,
    ) -> list[HistoricalCandle]:
        """Fetch and validate one bounded kline page."""
        normalized = symbol.strip().upper()
        if not normalized.isalnum() or not 1 <= len(normalized) <= 30:
            raise ValueError("symbol must contain only letters and digits")
        if interval not in INTERVALS:
            raise ValueError("Unsupported Binance kline interval")
        if not 1 <= limit <= MAX_KLINE_LIMIT:
            raise ValueError("Kline limit must be between 1 and 1000")
        if start_time.tzinfo is None or end_time.tzinfo is None:
            raise ValueError("Historical range timestamps must be timezone-aware")
        if start_time > end_time:
            raise ValueError("Historical range start must not be after end")
        client = self._client
        if client is None:
            raise RuntimeError("Use BinanceHistoricalRestClient as an async context manager")

        params: dict[str, str | int] = {
            "symbol": normalized,
            "interval": interval,
            "startTime": int(start_time.timestamp() * 1000),
            "endTime": int(end_time.timestamp() * 1000),
            "limit": limit,
        }
        try:
            response = await get_with_retry(
                client,
                f"{self._base_url}/api/v3/klines",
                params=params,
                policy=self._retry_policy,
            )
            response.raise_for_status()
            payload: Any = response.json()
        except MarketDataUnavailable:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise MarketDataUnavailable("Binance historical kline request failed") from exc

        if not isinstance(payload, list):
            raise MarketDataUnavailable("Binance returned an invalid kline response")

        received = datetime.now(UTC)
        current_time = now or received
        if current_time.tzinfo is None or current_time.utcoffset() is None:
            raise ValueError("Current time must be timezone-aware")
        current_time = current_time.astimezone(UTC)
        candles: list[HistoricalCandle] = []
        try:
            for row in payload:
                if not isinstance(row, list) or len(row) != 12:
                    raise ValueError("Kline row must contain all 12 Binance fields")
                open_time = parse_utc_milliseconds(int(row[0]))
                close_time = parse_utc_milliseconds(int(row[6]))
                expected_close = interval_close_time(open_time, interval)
                if close_time != expected_close:
                    raise ValueError("Binance kline close time is inconsistent")
                candles.append(
                    HistoricalCandle(
                        symbol=normalized,
                        interval=interval,
                        open_time=open_time,
                        close_time=close_time,
                        open=row[1],
                        high=row[2],
                        low=row[3],
                        close=row[4],
                        base_volume=row[5],
                        quote_volume=row[7],
                        trade_count=int(row[8]),
                        taker_buy_base_volume=row[9],
                        taker_buy_quote_volume=row[10],
                        received_time=received,
                        is_closed=close_time < current_time,
                    )
                )
        except (TypeError, ValueError, OverflowError) as exc:
            raise MarketDataUnavailable("Binance returned an invalid OHLCV candle") from exc

        if any(
            left.open_time >= right.open_time
            for left, right in zip(candles, candles[1:], strict=False)
        ):
            raise MarketDataUnavailable("Binance returned duplicate or out-of-order candles")
        return candles
