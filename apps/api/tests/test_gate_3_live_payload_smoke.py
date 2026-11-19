"""Temporary live smoke tests for Baymax's public Binance Spot parsers."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal

from app.market_data.binance_rest import BinanceSpotRestClient
from app.market_data.binance_stream import BinanceSpotTradeStream
from app.market_data.models import PriceEvent

SYMBOL = "BTCUSDT"
MAX_EVENT_AGE_MS = 3_000
NETWORK_TIMEOUT_SECONDS = 20.0


def _validated_report(event: PriceEvent, *, expected_source: str) -> dict[str, object]:
    """Assert the live adapter produced a complete, fresh canonical event."""
    now = datetime.now(UTC)
    age_ms = int((now - event.market_event_timestamp).total_seconds() * 1000)

    assert event.exchange == "BINANCE"
    assert event.market == "SPOT"
    assert event.symbol == SYMBOL
    assert event.source == expected_source
    assert isinstance(event.price, Decimal) and event.price.is_finite() and event.price > 0
    assert event.event_id is not None and event.event_id.isdigit()
    assert event.market_event_timestamp.tzinfo is not None
    assert event.received_timestamp.tzinfo is not None
    assert 0 <= age_ms <= MAX_EVENT_AGE_MS, (
        f"{expected_source} event age {age_ms}ms exceeds {MAX_EVENT_AGE_MS}ms"
    )

    if expected_source == "binance_spot_websocket":
        assert event.exchange_event_timestamp is not None
        assert event.exchange_event_timestamp.tzinfo is not None

    return {
        "status": "passed",
        "source": event.source,
        "symbol": event.symbol,
        "price": str(event.price),
        "trade_id": event.event_id,
        "market_event_timestamp": event.market_event_timestamp.isoformat(),
        "exchange_event_timestamp": (
            event.exchange_event_timestamp.isoformat()
            if event.exchange_event_timestamp is not None
            else None
        ),
        "received_timestamp": event.received_timestamp.isoformat(),
        "event_age_ms": age_ms,
        "canonical_model": "PriceEvent",
    }


async def _rest_smoke() -> dict[str, object]:
    async with BinanceSpotRestClient(timeout_seconds=8.0) as client:
        event = await asyncio.wait_for(
            client.latest_trade(SYMBOL),
            timeout=NETWORK_TIMEOUT_SECONDS,
        )
    return _validated_report(event, expected_source="binance_spot_rest")


async def _websocket_smoke() -> dict[str, object]:
    stream = BinanceSpotTradeStream()
    events = stream.listen(SYMBOL)
    try:
        event = await asyncio.wait_for(
            anext(events),
            timeout=NETWORK_TIMEOUT_SECONDS,
        )
    finally:
        await events.aclose()
    return _validated_report(event, expected_source="binance_spot_websocket")


def test_live_binance_spot_rest_and_websocket_payload_parsing() -> None:
    """Fetch real public trades and validate both production parser outputs."""
    results = {
        "rest": asyncio.run(_rest_smoke()),
        "websocket": asyncio.run(_websocket_smoke()),
        "credentials_used": False,
        "private_endpoints_used": False,
        "database_writes": False,
        "trading_operations": False,
    }
    print(json.dumps(results, indent=2))
