"""On-demand current-price retrieval and consume-time freshness enforcement."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Protocol

from app.market_data.binance_rest import BinanceSpotRestClient
from app.market_data.binance_stream import BinanceSpotTradeStream
from app.market_data.freshness import MarketDataUnavailable, validate_price_event
from app.market_data.models import PriceEvent, ValidatedPrice


class LatestTradeClient(Protocol):
    """Minimal injectable interface for a timestamped latest-trade source."""

    async def latest_trade(self, symbol: str) -> PriceEvent: ...


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
        stream: BinanceSpotTradeStream | None = None,
    ) -> None:
        self._rest: LatestTradeClient = rest_client or BinanceSpotRestClient()
        self._stream = stream or BinanceSpotTradeStream()
        self._events: dict[str, PriceEvent] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._stream_healthy: set[str] = set()
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
        self._stream_healthy.clear()
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
                self._consume_stream(normalized), name=f"binance-spot-{normalized.lower()}"
            )

    async def _consume_stream(self, symbol: str) -> None:
        try:
            async for event in self._stream.listen(symbol):
                self._events[symbol] = event
                self._stream_healthy.add(symbol)
        except asyncio.CancelledError:
            raise
        finally:
            self._stream_healthy.discard(symbol)

    async def get_current_price(
        self,
        symbol: str,
        *,
        clock_healthy: bool,
        now: datetime | None = None,
    ) -> ValidatedPrice:
        """Return a price only if it is fresh at this exact consumption boundary.

        A stale WebSocket cache triggers one timestamped REST latest-trade
        recovery attempt. The REST result is independently freshness-checked.
        """
        normalized = symbol.strip().upper()
        if not normalized.isalnum():
            raise ValueError("symbol must contain only letters and digits")
        if not self._started:
            await self.start()

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
        return validate_price_event(
            recovered,
            now=now,
            source_healthy=True,
            clock_healthy=clock_healthy,
        )
