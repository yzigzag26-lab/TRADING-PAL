"""Deterministic tests for Binance historical OHLCV validation and gap recovery."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError

from app.api.v1.endpoints.analysis import HistoricalAnalysisRequest
from app.market_data.binance_historical_rest import BinanceHistoricalRestClient
from app.market_data.candles import (
    HistoricalCandle,
    HistoricalCandleSeries,
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
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal("95"),
        close=Decimal(close),
        base_volume=Decimal("10.5"),
        quote_volume=Decimal("1050"),
        trade_count=12,
        taker_buy_base_volume=Decimal("4.5"),
        taker_buy_quote_volume=Decimal("450"),
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
        rest = BinanceHistoricalRestClient(
            base_url="https://test.invalid",
            client=client,
        )
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
        with pytest.raises(MarketDataUnavailable, match="HTTP 418|HTTP 429"):
            await rest.klines("BTCUSDT", "1m", start_time=START, end_time=START)
        await client.aclose()

    asyncio.run(run())


def test_historical_klines_retries_http_429(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        open_ms = int(START.timestamp() * 1000)
        close_ms = open_ms + 60_000 - 1
        calls = 0

        async def sleep(_: float) -> None:
            return None

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(429, headers={"Retry-After": "0"})
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

        monkeypatch.setattr("app.market_data.rest_retry.asyncio.sleep", sleep)
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        rest = BinanceHistoricalRestClient(base_url="https://test.invalid", client=client)
        rows = await rest.klines(
            "BTCUSDT",
            "1m",
            start_time=START,
            end_time=START,
            now=START + timedelta(minutes=2),
        )
        assert calls == 2
        assert len(rows) == 1
        assert rows[0].close == Decimal("101")
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


def test_expected_open_times_stops_at_configured_limit_for_large_ranges() -> None:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="exceeds maximum"):
        expected_open_times(start, end, "1s", max_count=100)


def test_historical_request_rejects_large_ranges_before_full_enumeration() -> None:
    with pytest.raises(ValidationError, match="exceeds maximum"):
        HistoricalAnalysisRequest(
            symbol="BTCUSDT",
            interval="1s",
            start_time=datetime(2020, 1, 1, tzinfo=UTC),
            end_time=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_candle_series_requires_exact_interval_continuity() -> None:
    rows = tuple(candle(START + timedelta(minutes=index)) for index in range(3))
    result = HistoricalCandleSeries(
        symbol="BTCUSDT",
        interval="1m",
        requested_start=START,
        requested_end=START + timedelta(minutes=2),
        candles=rows,
        missing_open_times=(),
        complete=True,
        recovery_attempts=0,
    )
    assert result.complete is True
    assert len(result.candles) == 3


def test_candle_series_rejects_false_complete_flag() -> None:
    with pytest.raises(ValidationError, match="completeness flag"):
        HistoricalCandleSeries(
            symbol="BTCUSDT",
            interval="1m",
            requested_start=START,
            requested_end=START + timedelta(minutes=2),
            candles=(candle(START), candle(START + timedelta(minutes=2))),
            missing_open_times=(START + timedelta(minutes=1),),
            complete=True,
            recovery_attempts=0,
        )


def test_candle_series_rejects_inaccurate_missing_interval_list() -> None:
    with pytest.raises(ValidationError, match="Missing candle timestamps"):
        HistoricalCandleSeries(
            symbol="BTCUSDT",
            interval="1m",
            requested_start=START,
            requested_end=START + timedelta(minutes=2),
            candles=(candle(START),),
            missing_open_times=(START + timedelta(minutes=2),),
            complete=False,
            recovery_attempts=0,
        )


def test_candle_series_rejects_out_of_range_candle() -> None:
    with pytest.raises(ValidationError, match="outside the requested range"):
        HistoricalCandleSeries(
            symbol="BTCUSDT",
            interval="1m",
            requested_start=START,
            requested_end=START + timedelta(minutes=1),
            candles=(candle(START), candle(START + timedelta(minutes=2))),
            missing_open_times=(),
            complete=True,
            recovery_attempts=0,
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"open": "0"},
        {"close": "-1"},
        {"high": "NaN"},
        {"quote_volume": "-0.01"},
        {"taker_buy_quote_volume": "1001"},
        {"trade_count": -1},
        {"close_time": START + timedelta(minutes=2)},
        {"open_time": START + timedelta(seconds=1)},
    ],
)
def test_invalid_or_incomplete_candle_fields_fail_closed(
    changes: dict[str, object],
) -> None:
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


def test_binance_kline_parser_distinguishes_open_and_closed_boundaries() -> None:
    async def run() -> None:
        open_ms = int(START.timestamp() * 1000)
        close_ms = open_ms + 60_000 - 1
        row = [
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

        async def fetch_at(now: datetime) -> HistoricalCandle:
            client = httpx.AsyncClient(
                transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[row]))
            )
            rest = BinanceHistoricalRestClient(
                base_url="https://test.invalid",
                client=client,
            )
            result = await rest.klines(
                "BTCUSDT",
                "1m",
                start_time=START,
                end_time=START,
                now=now,
            )
            await client.aclose()
            return result[0]

        before_close = await fetch_at(START + timedelta(minutes=1) - timedelta(milliseconds=1))
        at_next_open = await fetch_at(START + timedelta(minutes=1))
        assert before_close.is_closed is False
        assert at_next_open.is_closed is True

    asyncio.run(run())


def test_binance_kline_parser_rejects_truncated_row() -> None:
    async def run() -> None:
        open_ms = int(START.timestamp() * 1000)
        close_ms = open_ms + 60_000 - 1
        row = [
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
        ]
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[row]))
        )
        rest = BinanceHistoricalRestClient(
            base_url="https://test.invalid",
            client=client,
        )
        with pytest.raises(MarketDataUnavailable, match="invalid OHLCV candle"):
            await rest.klines(
                "BTCUSDT",
                "1m",
                start_time=START,
                end_time=START,
                now=START + timedelta(minutes=2),
            )
        await client.aclose()

    asyncio.run(run())
