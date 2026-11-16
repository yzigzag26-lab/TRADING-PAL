"""Mocked tests for Binance Spot REST recovery and on-demand consumption."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from app.market_data.binance_rest import BinanceSpotRestClient
from app.market_data.freshness import MarketDataUnavailable
from app.market_data.models import PriceEvent
from app.market_data.service import BinanceMarketDataService

NOW = datetime(2026, 11, 16, 12, 0, 0, tzinfo=UTC)


def test_rest_latest_trade_preserves_source_timestamp() -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/v3/trades"
            assert request.url.params["symbol"] == "BTCUSDT"
            return httpx.Response(
                200,
                json=[{"id": 123, "price": "95000.12", "time": int(NOW.timestamp() * 1000)}],
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        rest = BinanceSpotRestClient(base_url="https://test.invalid", client=client)
        event = await rest.latest_trade("btcusdt")
        assert event.symbol == "BTCUSDT"
        assert event.price == Decimal("95000.12")
        assert event.market_event_timestamp == NOW
        assert event.event_id == "123"
        await client.aclose()

    asyncio.run(run())


@pytest.mark.parametrize("status", [418, 429])
def test_rest_rate_limit_fails_closed(status: int) -> None:
    async def run() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(status, headers={"Retry-After": "10"})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        rest = BinanceSpotRestClient(base_url="https://test.invalid", client=client)
        with pytest.raises(MarketDataUnavailable, match="rate limited"):
            await rest.latest_trade("BTCUSDT")
        await client.aclose()

    asyncio.run(run())


def test_stale_rest_trade_is_rejected_by_service() -> None:
    class FakeRest:
        async def latest_trade(self, symbol: str) -> PriceEvent:
            return PriceEvent(
                symbol=symbol,
                price="95000",
                market_event_timestamp=NOW - timedelta(seconds=4),
                received_timestamp=NOW,
                source="binance_spot_rest",
                event_id="old-trade",
            )

    async def run() -> None:
        service = BinanceMarketDataService(rest_client=FakeRest())
        with pytest.raises(MarketDataUnavailable, match="older than 3 seconds"):
            await service.get_current_price("BTCUSDT", clock_healthy=True, now=NOW)

    asyncio.run(run())


def test_general_requests_do_not_fetch_unless_service_is_called() -> None:
    class FakeRest:
        calls = 0

        async def latest_trade(self, symbol: str) -> PriceEvent:
            self.calls += 1
            raise AssertionError("REST should not be called")

    rest = FakeRest()
    service = BinanceMarketDataService(rest_client=rest)
    assert rest.calls == 0
    assert service._events == {}

def test_stale_websocket_cache_is_recovered_from_rest_and_revalidated() -> None:
    class FakeRest:
        calls = 0

        async def latest_trade(self, symbol: str) -> PriceEvent:
            self.calls += 1
            return PriceEvent(
                symbol=symbol,
                price="95123.45",
                market_event_timestamp=NOW - timedelta(milliseconds=500),
                received_timestamp=NOW,
                source="binance_spot_rest",
                event_id="fresh-rest-trade",
            )

    class IdleStream:
        async def listen(self, symbol: str):
            if False:
                yield PriceEvent(
                    symbol=symbol,
                    price="1",
                    market_event_timestamp=NOW,
                    received_timestamp=NOW,
                    source="binance_spot_websocket",
                )
            await asyncio.Event().wait()

    async def run() -> None:
        rest = FakeRest()
        service = BinanceMarketDataService(rest_client=rest, stream=IdleStream())  # type: ignore[arg-type]
        service._started = True
        service._events["BTCUSDT"] = PriceEvent(
            symbol="BTCUSDT",
            price="90000",
            market_event_timestamp=NOW - timedelta(seconds=5),
            received_timestamp=NOW,
            source="binance_spot_websocket",
            event_id="stale-stream-trade",
        )
        service._stream_healthy.add("BTCUSDT")

        result = await service.get_current_price("BTCUSDT", clock_healthy=True, now=NOW)
        assert rest.calls == 1
        assert result.price == Decimal("95123.45")
        assert result.source == "binance_spot_rest"
        await service.close()

    asyncio.run(run())
