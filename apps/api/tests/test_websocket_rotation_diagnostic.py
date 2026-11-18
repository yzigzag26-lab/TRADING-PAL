from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.api.v1.router import api_router
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

    assert service.stream_status("BTCUSDT") == {
        "connected": True,
        "healthy": True,
        "event_source": "binance_spot_websocket",
        "event_id": "123456",
        "market_event_timestamp": (
            service._events["BTCUSDT"].market_event_timestamp.isoformat()
        ),
    }
    assert service.stream_status("ETHUSDT") == {
        "connected": False,
        "healthy": False,
        "event_source": None,
        "event_id": None,
        "market_event_timestamp": None,
    }


def test_forced_rotation_diagnostic_is_registered_on_versioned_api() -> None:
    assert any(
        getattr(route, "path", None)
        == "/api/v1/diagnostics/gate-3/websocket-rotation"
        for route in api_router.routes
    )
