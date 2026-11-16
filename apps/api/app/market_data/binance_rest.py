"""Public Binance Spot REST adapter for timestamped latest-trade recovery."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.market_data.freshness import MarketDataUnavailable
from app.market_data.models import PriceEvent

BINANCE_SPOT_REST_BASE_URL = "https://data-api.binance.vision"


class BinanceSpotRestClient:
    """Small read-only REST client; no API credentials or signed requests."""

    def __init__(
        self,
        *,
        base_url: str = BINANCE_SPOT_REST_BASE_URL,
        timeout_seconds: float = 4.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> BinanceSpotRestClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def latest_trade(self, symbol: str) -> PriceEvent:
        """Fetch the most recent trade, retaining Binance trade and event times."""
        normalized = symbol.strip().upper()
        if not normalized.isalnum() or not 1 <= len(normalized) <= 30:
            raise ValueError("symbol must contain only letters and digits")
        client = self._client
        if client is None:
            raise RuntimeError("Use BinanceSpotRestClient as an async context manager")

        try:
            response = await client.get(
                f"{self._base_url}/api/v3/trades",
                params={"symbol": normalized, "limit": 1},
            )
            if response.status_code in (418, 429):
                retry_after = response.headers.get("Retry-After")
                raise MarketDataUnavailable(
                    f"Binance REST rate limited the request (HTTP {response.status_code}); "
                    f"Retry-After={retry_after or 'not-provided'}"
                )
            response.raise_for_status()
            payload: Any = response.json()
        except MarketDataUnavailable:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise MarketDataUnavailable("Binance latest-trade REST request failed") from exc

        if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
            raise MarketDataUnavailable("Binance returned an incomplete latest-trade response")

        trade = payload[0]
        try:
            trade_time = datetime.fromtimestamp(int(trade["time"]) / 1000, tz=UTC)
            received_time = datetime.now(UTC)
            trade_id = str(trade["id"])
            price = Decimal(str(trade["price"]))
        except (KeyError, TypeError, ValueError, OverflowError, InvalidOperation) as exc:
            raise MarketDataUnavailable("Binance latest-trade payload is invalid") from exc

        return PriceEvent(
            symbol=normalized,
            price=price,
            market_event_timestamp=trade_time,
            exchange_event_timestamp=trade_time,
            received_timestamp=received_time,
            source="binance_spot_rest",
            event_id=trade_id,
        )
