"""Reconnectable public Binance Spot trade-stream adapter."""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, WebSocketException

from app.market_data.freshness import MarketDataUnavailable
from app.market_data.models import PriceEvent

BINANCE_SPOT_WS_BASE_URL = "wss://data-stream.binance.vision"


class BinanceSpotTradeStream:
    """Yield validated-shape trade events and reconnect with bounded backoff."""

    def __init__(self, *, base_url: str = BINANCE_SPOT_WS_BASE_URL) -> None:
        self._base_url = base_url.rstrip("/")

    async def listen(self, symbol: str) -> AsyncIterator[PriceEvent]:
        normalized = symbol.strip().lower()
        if not normalized.isalnum() or not 1 <= len(normalized) <= 30:
            raise ValueError("symbol must contain only letters and digits")
        url = f"{self._base_url}/ws/{normalized}@trade"
        attempt = 0

        while True:
            try:
                async with connect(
                    url,
                    ping_interval=20,
                    ping_timeout=60,
                    close_timeout=10,
                    max_size=1_048_576,
                ) as websocket:
                    attempt = 0
                    async for message in websocket:
                        received_time = datetime.now(UTC)
                        try:
                            payload: Any = json.loads(message)
                            if not isinstance(payload, dict):
                                raise ValueError("trade event must be an object")
                            if str(payload["s"]).upper() != normalized.upper():
                                raise ValueError("trade event symbol mismatch")
                            event_time = datetime.fromtimestamp(int(payload["E"]) / 1000, tz=UTC)
                            trade_time = datetime.fromtimestamp(int(payload["T"]) / 1000, tz=UTC)
                            yield PriceEvent(
                                symbol=str(payload["s"]),
                                price=str(payload["p"]),
                                market_event_timestamp=trade_time,
                                exchange_event_timestamp=event_time,
                                received_timestamp=received_time,
                                source="binance_spot_websocket",
                                event_id=str(payload["t"]),
                            )
                        except (KeyError, TypeError, ValueError, OverflowError) as exc:
                            raise MarketDataUnavailable(
                                "Binance WebSocket trade payload failed validation"
                            ) from exc
            except asyncio.CancelledError:
                raise
            except (ConnectionClosed, OSError, WebSocketException):
                attempt += 1
                ceiling = min(30.0, 0.5 * (2 ** min(attempt, 6)))
                await asyncio.sleep(random.uniform(0.0, ceiling))
