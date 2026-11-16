"""Deterministic tests for Binance historical OHLCV validation and gap recovery."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError

from app.market_data.binance_historical_rest import BinanceHistoricalRestClient
from app.market_data.candles import (
    HistoricalCandle,
    expected_open_times,
    interval_close_time,
)
from app.market_data.freshness import MarketDataUnavailable
from app.market_data.historical_service import BinanceHistoricalCandleService

START = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


def candle(open_time: datetime, *, close: str = "101") -> HistoricalCandle:
    return HistoricalCandle(
        symbol="BTCUSDT",
        interval="1m",
        open_time=open_time,
        close_time=interval_close_time(open_time, "1m"),
        open="100",
        high="105",
        low="95",
        close=close,
        base_volume="10.5",
        quote_volume="1050",
        trade_count=12,
        taker_buy_base_volume="4.5",
        taker_buy_quote_volume="450",
        received_time=START + timedelta(minutes=5),
        is_closed=True,
    )


def test_interval_range_requires_aligned_boundaries() -> None:
    assert len(expected_open_times(START, START + timedelta(minutes=4), "1m")) == 5
    with pytest.raises(ValueError, match="align"):
        expected_open_times(START + timedelta(seconds=1), START + timedelta(minutes=2), "1m")


def test_month_interval_advances_calendar_month() -> None:
    january = datetime(2026, 1, 1, tzinfo=UTC)
    assert len(expected_open_times(january, datetime(2026, 3, 1, tzinfo=UTC), "1M")) == 3


def test_candle_validates_decimal_ohlcv_and_interval_close() -> None:
    item = candle(START)
    assert item.open == Decimal("100")
    assert item.base_volume == Decimal("10.5")
    assert item.close_time == START + timedelta(minutes=1) - timedelta(milliseconds=1)


@pytest.mark.parametrize(
    "changes",
    [
        {"low": "101"},
        {"high": "99"},
        {"base_volume": "-1"},
        {"taker_buy_base_volume": "11"},
        {"open": "NaN"},
    ],
)
def test_invalid_ohlcv_is_rejected(changes: dict[str, str]) -> None:
    values: dict[str, object] = {
        "symbol": "BTCUSDT",
        "interval": "1m",
        "open_time": START,
        "close_time": interval_close_time(START, "1m"),
        "open": "100",
        "high": "105",
        "low": "95",
        "close": "101",
        "base_volume": "10",
        "quote_volume": "1000",
        "trade_count": 5,
        "taker_buy_base_volume": "4",
        "taker_buy_quote_volume": "400",
        "received_time": START,
        "is_closed": True,
    }
    values.update(changes)
    with pytest.raises(ValidationError):
        HistoricalCandle.model_validate(values)


def test_binance_kline_parser_preserves_ohlcv_and_closed_state() -> None:
    async def run() -> None:
        open_ms = int(START.timestamp() * 1000)
        close_ms = open_ms + 60_000 - 1

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/v3/klines"
            assert request.url.params["symbol"] == "BTCUSDT"
            assert request.url.params["interval"] == "1m"
            return httpx.Response(
                200,
                json=[
                    [
                        open_ms,
                        "100",
                        "105",
                        "95",
                        "101",
                        "10.5",
                        close_ms,
                        "1050",
                        12,
                        "4.5",
                        "450",
                        "0",
                    ]
                ],
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        rest = BinanceHistoricalRestClient(base_url="https://test.invalid", client=client)
        rows = await rest.klines(
            "btcusdt",
            "1m",
            start_time=START,
            end_time=START,
            now=START + timedelta(minutes=2),
        )
        assert len(rows) == 1
        assert rows[0].symbol == "BTCUSDT"
        assert rows[0].close == Decimal("101")
        assert rows[0].is_closed is True
        await client.aclose()

    asyncio.run(run())


@pytest.mark.parametrize("status", [418, 429])
def test_historical_rest_rate_limit_fails_closed(status: int) -> None:
    async def run() -> None:
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(status, headers={"Retry-After": "15"})
            )
        )
        rest = BinanceHistoricalRestClient(base_url="https://test.invalid", client=client)
        with pytest.raises(MarketDataUnavailable, match="rate limited"):
            await rest.klines("BTCUSDT", "1m", start_time=START, end_time=START)
        await client.aclose()

    asyncio.run(run())


def test_historical_service_detects_and_recovers_a_missing_candle() -> None:
    class FakeRest:
        calls: list[tuple[datetime, datetime]] = []

        async def klines(
            self,
            symbol: str,
            interval: str,
            *,
            start_time: datetime,
            end_time: datetime,
            limit: int = 1000,
            now: datetime | None = None,
        ) -> list[HistoricalCandle]:
            self.calls.append((start_time, end_time))
            all_rows = {
                START + timedelta(minutes=index): candle(START + timedelta(minutes=index))
                for index in range(5)
            }
            if len(self.calls) == 1:
                return [
                    all_rows[START],
                    all_rows[START + timedelta(minutes=1)],
                    all_rows[START + timedelta(minutes=3)],
                    all_rows[START + timedelta(minutes=4)],
                ]
            return [all_rows[start_time]] if start_time in all_rows else []

    async def run() -> None:
        rest = FakeRest()
        service = BinanceHistoricalCandleService(rest_client=rest)
        result = await service.fetch(
            "BTCUSDT",
            "1m",
            start_time=START,
            end_time=START + timedelta(minutes=4),
        )
        assert result.complete is True
        assert len(result.candles) == 5
        assert result.missing_open_times == ()
        assert result.recovery_attempts == 1
        assert len(rest.calls) == 2

    asyncio.run(run())


def test_historical_service_reports_unrecovered_gaps_without_fabrication() -> None:
    class FakeRest:
        async def klines(
            self,
            symbol: str,
            interval: str,
            *,
            start_time: datetime,
            end_time: datetime,
            limit: int = 1000,
            now: datetime | None = None,
        ) -> list[HistoricalCandle]:
            if start_time == START + timedelta(minutes=2):
                return []
            return [candle(START), candle(START + timedelta(minutes=1))]

    async def run() -> None:
        service = BinanceHistoricalCandleService(rest_client=FakeRest(), recovery_attempts=1)
        result = await service.fetch(
            "BTCUSDT",
            "1m",
            start_time=START,
            end_time=START + timedelta(minutes=2),
        )
        assert result.complete is False
        assert len(result.candles) == 2
        assert result.missing_open_times == (START + timedelta(minutes=2),)
        assert result.recovery_attempts == 1

    asyncio.run(run())


def test_historical_service_enforces_range_size_limit() -> None:
    async def run() -> None:
        class EmptyRest:
            async def klines(
                self,
                symbol: str,
                interval: str,
                *,
                start_time: datetime,
                end_time: datetime,
                limit: int = 1000,
                now: datetime | None = None,
            ) -> list[HistoricalCandle]:
                return []

        service = BinanceHistoricalCandleService(rest_client=EmptyRest(), max_candles=2)
        with pytest.raises(ValueError, match="exceeds"):
            await service.fetch(
                "BTCUSDT",
                "1m",
                start_time=START,
                end_time=START + timedelta(minutes=2),
            )

    asyncio.run(run())
