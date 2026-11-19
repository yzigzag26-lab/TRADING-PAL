from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.market_data.models import PriceEvent
from app.market_data.service import BinanceMarketDataService


def test_market_data_service_exposes_read_only_stream_status() -> None:
    service = BinanceMarketDataService()
    service._stream_connected.add("BTCUSDT")
    service._stream_healthy.add("BTCUSDT")
    service._events["BTCUSDT"] = PriceEvent(
        symbol="BTCUSDT",
        price=Decimal("65000.00"),
        market_event_timestamp=datetime.now(UTC),
        received_timestamp=datetime.now(UTC),
        source="binance_spot_websocket",
        event_id="123456",
    )

    event_timestamp = service._events["BTCUSDT"].market_event_timestamp.isoformat()
    assert service.stream_status("BTCUSDT") == {
        "connected": True,
        "healthy": True,
        "event_source": "binance_spot_websocket",
        "event_id": "123456",
        "market_event_timestamp": event_timestamp,
    }
    assert service.stream_status("ETHUSDT") == {
        "connected": False,
        "healthy": False,
        "event_source": None,
        "event_id": None,
        "market_event_timestamp": None,
    }


def test_rotation_diagnostic_uses_extended_stage_and_overall_timeouts() -> None:
    from app.api.v1.endpoints.websocket_rotation import (
        FORCED_DISCONNECT_TIMEOUT_SECONDS,
        INITIAL_TRADE_TIMEOUT_SECONDS,
        POST_RECONNECT_TRADE_TIMEOUT_SECONDS,
        RESUBSCRIPTION_TIMEOUT_SECONDS,
        ROTATION_TEST_CLEANUP_TIMEOUT_SECONDS,
        ROTATION_TEST_TIMEOUT_SECONDS,
    )

    assert INITIAL_TRADE_TIMEOUT_SECONDS == 30.0
    assert FORCED_DISCONNECT_TIMEOUT_SECONDS == 30.0
    assert RESUBSCRIPTION_TIMEOUT_SECONDS == 30.0
    assert POST_RECONNECT_TRADE_TIMEOUT_SECONDS == 30.0
    assert ROTATION_TEST_TIMEOUT_SECONDS == 120.0
    assert ROTATION_TEST_CLEANUP_TIMEOUT_SECONDS == 15.0


def test_rotation_wait_timeout_identifies_the_failed_lifecycle_stage() -> None:
    import asyncio

    import pytest

    from app.api.v1.endpoints.websocket_rotation import _wait_until

    async def wait_for_never_ready_stage() -> None:
        await _wait_until(
            lambda: False,
            timeout_seconds=0.01,
            description="replacement WebSocket subscription",
        )

    with pytest.raises(TimeoutError, match="replacement WebSocket subscription"):
        asyncio.run(wait_for_never_ready_stage())
