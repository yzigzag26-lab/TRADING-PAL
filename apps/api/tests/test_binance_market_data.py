"""Mocked tests for Binance Spot REST recovery and on-demand consumption."""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from app.market_data.binance_rest import BinanceSpotRestClient
from app.market_data.binance_stream import PLANNED_RECONNECT_SECONDS, BinanceSpotTradeStream
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
                price=Decimal("95000"),
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
                price=Decimal("95123.45"),
                market_event_timestamp=NOW - timedelta(milliseconds=500),
                received_timestamp=NOW,
                source="binance_spot_rest",
                event_id="fresh-rest-trade",
            )

    class IdleStream:
        async def listen(
            self,
            symbol: str,
            *,
            on_connection_state: Callable[[bool], Awaitable[None]],
        ) -> AsyncIterator[PriceEvent]:
            await on_connection_state(True)
            if False:
                yield PriceEvent(
                    symbol=symbol,
                    price=Decimal("1"),
                    market_event_timestamp=NOW,
                    received_timestamp=NOW,
                    source="binance_spot_websocket",
                )
            try:
                await asyncio.Event().wait()
            finally:
                await on_connection_state(False)

    async def run() -> None:
        rest = FakeRest()
        service = BinanceMarketDataService(
            rest_client=rest,
            stream=IdleStream(),
        )
        service._started = True
        service._events["BTCUSDT"] = PriceEvent(
            symbol="BTCUSDT",
            price=Decimal("90000"),
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


def _trade_event(trade_id: int, *, price: str = "95000") -> PriceEvent:
    return PriceEvent(
        symbol="BTCUSDT",
        price=Decimal(price),
        market_event_timestamp=NOW + timedelta(milliseconds=trade_id),
        received_timestamp=NOW,
        source="binance_spot_websocket",
        event_id=str(trade_id),
    )


def test_stream_ignores_duplicate_and_out_of_order_trade_ids() -> None:
    class FakeRest:
        async def latest_trade(self, symbol: str) -> PriceEvent:
            raise AssertionError("No sequence gap should trigger REST")

    class SequenceStream:
        async def listen(
            self,
            symbol: str,
            *,
            on_connection_state: Callable[[bool], Awaitable[None]],
        ) -> AsyncIterator[PriceEvent]:
            await on_connection_state(True)
            try:
                yield _trade_event(100, price="100")
                yield _trade_event(100, price="101")
                yield _trade_event(99, price="102")
                yield _trade_event(101, price="103")
                await asyncio.Event().wait()
            finally:
                await on_connection_state(False)

    async def run() -> None:
        service = BinanceMarketDataService(
            rest_client=FakeRest(),
            stream=SequenceStream(),  # type: ignore[arg-type]
        )
        await service.start_symbol_stream("BTCUSDT")
        for _ in range(20):
            if service._last_trade_ids.get("BTCUSDT") == 101:
                break
            await asyncio.sleep(0)
        assert service._last_trade_ids["BTCUSDT"] == 101
        assert service._events["BTCUSDT"].price == Decimal("103")
        assert "BTCUSDT" in service._stream_healthy
        await service.close()

    asyncio.run(run())


def test_stream_trade_id_gap_requires_rest_reconciliation() -> None:
    class FakeRest:
        calls = 0

        async def latest_trade(self, symbol: str) -> PriceEvent:
            self.calls += 1
            return PriceEvent(
                symbol=symbol,
                price=Decimal("105"),
                market_event_timestamp=NOW + timedelta(milliseconds=202),
                received_timestamp=NOW,
                source="binance_spot_rest",
                event_id="202",
            )

    class GapStream:
        async def listen(
            self,
            symbol: str,
            *,
            on_connection_state: Callable[[bool], Awaitable[None]],
        ) -> AsyncIterator[PriceEvent]:
            await on_connection_state(True)
            try:
                yield _trade_event(200, price="100")
                yield _trade_event(202, price="102")
                await asyncio.Event().wait()
            finally:
                await on_connection_state(False)

    async def run() -> None:
        rest = FakeRest()
        service = BinanceMarketDataService(
            rest_client=rest,
            stream=GapStream(),  # type: ignore[arg-type]
        )
        await service.start_symbol_stream("BTCUSDT")
        for _ in range(20):
            if rest.calls:
                break
            await asyncio.sleep(0)
        assert rest.calls == 1
        assert service._last_trade_ids["BTCUSDT"] == 202
        assert service._events["BTCUSDT"].source == "binance_spot_rest"
        assert service._events["BTCUSDT"].price == Decimal("105")
        assert "BTCUSDT" in service._stream_healthy
        await service.close()

    asyncio.run(run())


def test_disconnect_marks_stream_unhealthy_and_clears_cached_event() -> None:
    class FakeRest:
        async def latest_trade(self, symbol: str) -> PriceEvent:
            raise AssertionError("This test does not request a current price")

    class DisconnectStream:
        async def listen(
            self,
            symbol: str,
            *,
            on_connection_state: Callable[[bool], Awaitable[None]],
        ) -> AsyncIterator[PriceEvent]:
            await on_connection_state(True)
            yield _trade_event(300)
            await on_connection_state(False)
            await asyncio.Event().wait()

    async def run() -> None:
        service = BinanceMarketDataService(
            rest_client=FakeRest(),
            stream=DisconnectStream(),  # type: ignore[arg-type]
        )
        await service.start_symbol_stream("BTCUSDT")
        for _ in range(20):
            if "BTCUSDT" not in service._stream_connected:
                await asyncio.sleep(0)
                if "BTCUSDT" not in service._events:
                    break
            await asyncio.sleep(0)
        assert "BTCUSDT" not in service._stream_healthy
        assert "BTCUSDT" not in service._events
        await service.close()

    asyncio.run(run())


def test_stream_planned_rotation_is_before_binance_24_hour_limit() -> None:
    assert PLANNED_RECONNECT_SECONDS < 24 * 60 * 60
    assert PLANNED_RECONNECT_SECONDS == 23 * 60 * 60 + 50 * 60
    with pytest.raises(ValueError, match="must be positive"):
        BinanceSpotTradeStream(connection_lifetime_seconds=0)


def test_stream_rotates_connection_and_reports_state_transitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection_count = 0

    class FakeWebSocket:
        def __init__(self, connection_number: int) -> None:
            self.connection_number = connection_number
            self.recv_count = 0

        async def recv(self) -> str:
            self.recv_count += 1
            if self.recv_count > 1:
                await asyncio.Event().wait()
            timestamp = int(NOW.timestamp() * 1000) + self.connection_number
            return json.dumps(
                {
                    "s": "BTCUSDT",
                    "E": timestamp,
                    "T": timestamp,
                    "p": "95000.12",
                    "t": self.connection_number,
                }
            )

    class FakeConnection:
        def __init__(self, connection_number: int) -> None:
            self.websocket = FakeWebSocket(connection_number)

        async def __aenter__(self) -> FakeWebSocket:
            return self.websocket

        async def __aexit__(self, *_: object) -> None:
            return None

    def fake_connect(_: str, **__: object) -> FakeConnection:
        nonlocal connection_count
        connection_count += 1
        return FakeConnection(connection_count)

    monkeypatch.setattr("app.market_data.binance_stream.connect", fake_connect)

    async def run() -> None:
        states: list[bool] = []

        async def on_state(connected: bool) -> None:
            states.append(connected)

        stream = BinanceSpotTradeStream(connection_lifetime_seconds=0.01)
        iterator = stream.listen("BTCUSDT", on_connection_state=on_state)
        try:
            first = await anext(iterator)
            second = await asyncio.wait_for(anext(iterator), timeout=2)
            assert first.event_id == "1"
            assert second.event_id == "2"
            assert connection_count >= 2
            assert states[:3] == [True, False, True]
        finally:
            await iterator.aclose()

    asyncio.run(run())
