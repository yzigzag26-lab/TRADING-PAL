"""On-demand current-price retrieval and consume-time freshness enforcement."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from typing import Protocol

from app.market_data.binance_rest import BinanceSpotRestClient
from app.market_data.binance_stream import BinanceSpotTradeStream
from app.market_data.freshness import MarketDataUnavailable, validate_price_event
from app.market_data.models import PriceEvent, ValidatedPrice


class LatestTradeClient(Protocol):
    """Minimal injectable interface for a timestamped latest-trade source."""

    async def latest_trade(self, symbol: str) -> PriceEvent: ...


class TradeStream(Protocol):
    """Injectable live stream contract with explicit connection-state callbacks."""

    def listen(
        self,
        symbol: str,
        *,
        on_connection_state: Callable[[bool], Awaitable[None]],
    ) -> AsyncIterator[PriceEvent]: ...


class BinanceMarketDataService:
    """Single-process market-data service for the private Baymax deployment.

    The application/orchestrator calls get_current_price only when a request
    requires current market information. Educational and general questions
    must not call this service.
    """

    def __init__(
        self,
        *,
        rest_client: LatestTradeClient | None = None,
        stream: TradeStream | None = None,
    ) -> None:
        self._rest: LatestTradeClient = rest_client or BinanceSpotRestClient()
        self._stream = stream or BinanceSpotTradeStream()
        self._events: dict[str, PriceEvent] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._stream_connected: set[str] = set()
        self._stream_healthy: set[str] = set()
        self._last_trade_ids: dict[str, int] = {}
        self._owns_rest = rest_client is None
        self._started = False

    async def start(self) -> None:
        """Open the owned REST client; subscriptions remain demand-driven."""
        if not self._started:
            if self._owns_rest:
                await self._rest.__aenter__()  # type: ignore[attr-defined]
            self._started = True

    async def close(self) -> None:
        """Cancel streams and release the owned REST connection pool."""
        tasks = tuple(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._events.clear()
        self._stream_connected.clear()
        self._stream_healthy.clear()
        self._last_trade_ids.clear()
        if self._owns_rest and self._started:
            await self._rest.__aexit__(None, None, None)  # type: ignore[attr-defined]
        self._started = False

    async def start_symbol_stream(self, symbol: str) -> None:
        """Start one shared live trade stream for a normalized Spot symbol."""
        normalized = symbol.strip().upper()
        if not normalized.isalnum():
            raise ValueError("symbol must contain only letters and digits")
        if not self._started:
            await self.start()
        existing = self._tasks.get(normalized)
        if existing is None or existing.done():
            self._tasks[normalized] = asyncio.create_task(
                self._consume_stream(normalized),
                name=f"binance-spot-{normalized.lower()}",
            )

    @staticmethod
    def _numeric_trade_id(event: PriceEvent) -> int | None:
        if event.event_id is None or not event.event_id.isdigit():
            return None
        return int(event.event_id)

    async def _consume_stream(self, symbol: str) -> None:
        async def connection_state(connected: bool) -> None:
            if connected:
                self._stream_connected.add(symbol)
                # A connection is not healthy until a fresh event is accepted.
                self._stream_healthy.discard(symbol)
            else:
                self._stream_connected.discard(symbol)
                self._stream_healthy.discard(symbol)
                self._events.pop(symbol, None)

        try:
            async for event in self._stream.listen(
                symbol,
                on_connection_state=connection_state,
            ):
                previous = self._events.get(symbol)
                previous_id = self._last_trade_ids.get(symbol)
                current_id = self._numeric_trade_id(event)

                if previous is not None:
                    if event.market_event_timestamp < previous.market_event_timestamp:
                        continue
                    if (
                        event.market_event_timestamp == previous.market_event_timestamp
                        and current_id is not None
                        and previous_id is not None
                        and current_id <= previous_id
                    ):
                        continue

                if (
                    current_id is not None
                    and previous_id is not None
                    and current_id <= previous_id
                ):
                    continue

                if (
                    current_id is not None
                    and previous_id is not None
                    and current_id > previous_id + 1
                ):
                    # Trade IDs are sequence evidence. Do not accept a stream
                    # event across a gap until REST reconciles the latest trade.
                    self._stream_healthy.discard(symbol)
                    self._events.pop(symbol, None)
                    try:
                        recovered = await self._rest.latest_trade(symbol)
                    except MarketDataUnavailable:
                        continue
                    recovered_id = self._numeric_trade_id(recovered)
                    if recovered_id is None or recovered_id < current_id:
                        continue
                    self._events[symbol] = recovered
                    self._last_trade_ids[symbol] = recovered_id
                    if symbol in self._stream_connected:
                        self._stream_healthy.add(symbol)
                    continue

                self._events[symbol] = event
                if current_id is not None:
                    self._last_trade_ids[symbol] = current_id
                if symbol in self._stream_connected:
                    self._stream_healthy.add(symbol)
        except asyncio.CancelledError:
            raise
        finally:
            self._stream_connected.discard(symbol)
            self._stream_healthy.discard(symbol)
            self._events.pop(symbol, None)

    async def get_current_price(
        self,
        symbol: str,
        *,
        clock_healthy: bool,
        now: datetime | None = None,
    ) -> ValidatedPrice:
        """Return a price only if it is fresh at this exact consumption boundary.

        A stale or disconnected WebSocket cache triggers one timestamped REST
        latest-trade recovery attempt. The REST result is independently checked.
        """
        normalized = symbol.strip().upper()
        if not normalized.isalnum():
            raise ValueError("symbol must contain only letters and digits")
        if not self._started:
            await self.start()
        await self.start_symbol_stream(normalized)

        event = self._events.get(normalized)
        if event is not None:
            try:
                return validate_price_event(
                    event,
                    now=now,
                    source_healthy=normalized in self._stream_healthy,
                    clock_healthy=clock_healthy,
                )
            except MarketDataUnavailable:
                self._events.pop(normalized, None)

        recovered = await self._rest.latest_trade(normalized)
        self._events[normalized] = recovered
        recovered_id = self._numeric_trade_id(recovered)
        if recovered_id is not None:
            self._last_trade_ids[normalized] = recovered_id
        return validate_price_event(
            recovered,
            now=now,
            source_healthy=True,
            clock_healthy=clock_healthy,
        )
