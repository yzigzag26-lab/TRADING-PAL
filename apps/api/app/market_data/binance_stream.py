"""Reconnectable public Binance Spot trade-stream adapter."""

from __future__ import annotations

import asyncio
import json
import random
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, WebSocketException

from app.market_data.freshness import MarketDataUnavailable
from app.market_data.models import PriceEvent

BINANCE_SPOT_WS_BASE_URL = "wss://data-stream.binance.vision"
PLANNED_RECONNECT_SECONDS = 23 * 60 * 60 + 50 * 60
WEBSOCKET_PING_INTERVAL_SECONDS = 20
WEBSOCKET_PING_TIMEOUT_SECONDS = 60


class BinanceSpotTradeStream:
    """Yield validated trade events with bounded reconnect and planned rotation."""

    def __init__(
        self,
        *,
        base_url: str = BINANCE_SPOT_WS_BASE_URL,
        connection_lifetime_seconds: float = PLANNED_RECONNECT_SECONDS,
    ) -> None:
        if connection_lifetime_seconds <= 0:
            raise ValueError("connection_lifetime_seconds must be positive")
        self._base_url = base_url.rstrip("/")
        self._connection_lifetime_seconds = connection_lifetime_seconds

    async def listen(
        self,
        symbol: str,
        *,
        on_connection_state: Callable[[bool], Awaitable[None]] | None = None,
    ) -> AsyncGenerator[PriceEvent, None]:
        """Yield trades and report each connection transition to the service."""
        normalized = symbol.strip().lower()
        if not normalized.isalnum() or not 1 <= len(normalized) <= 30:
            raise ValueError("symbol must contain only letters and digits")
        url = f"{self._base_url}/ws/{normalized}@trade"
        attempt = 0

        while True:
            connection_started = time.monotonic()
            try:
                async with connect(
                    url,
                    ping_interval=WEBSOCKET_PING_INTERVAL_SECONDS,
                    ping_timeout=WEBSOCKET_PING_TIMEOUT_SECONDS,
                    close_timeout=10,
                    max_size=1_048_576,
                ) as websocket:
                    if on_connection_state is not None:
                        await on_connection_state(True)
                    deadline = time.monotonic() + self._connection_lifetime_seconds
                    try:
                        while True:
                            remaining = deadline - time.monotonic()
                            if remaining <= 0:
                                break
                            try:
                                message = await asyncio.wait_for(
                                    websocket.recv(),
                                    timeout=remaining,
                                )
                            except TimeoutError:
                                break
                            if message is None:
                                break

                            received_time = datetime.now(UTC)
                            try:
                                payload: Any = json.loads(message)
                                if not isinstance(payload, dict):
                                    raise ValueError("trade event must be an object")
                                if str(payload["s"]).upper() != normalized.upper():
                                    raise ValueError("trade event symbol mismatch")
                                event_time = datetime.fromtimestamp(
                                    int(payload["E"]) / 1000,
                                    tz=UTC,
                                )
                                trade_time = datetime.fromtimestamp(
                                    int(payload["T"]) / 1000,
                                    tz=UTC,
                                )
                                yield PriceEvent(
                                    symbol=str(payload["s"]),
                                    price=Decimal(str(payload["p"])),
                                    market_event_timestamp=trade_time,
                                    exchange_event_timestamp=event_time,
                                    received_timestamp=received_time,
                                    source="binance_spot_websocket",
                                    event_id=str(payload["t"]),
                                )
                            except (
                                KeyError,
                                TypeError,
                                ValueError,
                                OverflowError,
                                InvalidOperation,
                            ) as exc:
                                raise MarketDataUnavailable(
                                    "Binance WebSocket trade payload failed validation"
                                ) from exc
                    finally:
                        if on_connection_state is not None:
                            await on_connection_state(False)

                # Planned rotation follows a stable connection and avoids reconnect bursts.
                if time.monotonic() - connection_started >= 60:
                    attempt = 0
                else:
                    attempt += 1
                ceiling = min(30.0, 0.5 * (2 ** min(attempt, 6)))
                await asyncio.sleep(random.uniform(0.0, ceiling))
            except asyncio.CancelledError:
                raise
            except (ConnectionClosed, OSError, WebSocketException, MarketDataUnavailable):
                if time.monotonic() - connection_started >= 60:
                    attempt = 0
                attempt += 1
                ceiling = min(30.0, 0.5 * (2 ** min(attempt, 6)))
                await asyncio.sleep(random.uniform(0.0, ceiling))
