from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.market_data.freshness import MarketDataUnavailable
from app.market_data.models import ValidatedPrice
from app.market_data.service import BinanceMarketDataService
from app.orchestration.requests import (
    AnalysisInputUnavailable,
    AnalysisRequest,
    BaymaxRequestOrchestrator,
)


class FakeMarketData:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []
        self.started = False
        self.closed = False

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True

    async def get_current_price(self, symbol: str, *, clock_healthy: bool) -> ValidatedPrice:
        self.calls.append((symbol, clock_healthy))
        if not clock_healthy:
            raise MarketDataUnavailable("clock is unhealthy")
        now = datetime.now(UTC)
        return ValidatedPrice(
            exchange="BINANCE",
            market="SPOT",
            symbol=symbol,
            price=Decimal("95000.25"),
            market_event_timestamp=now,
            received_timestamp=now,
            validated_timestamp=now,
            age_ms_at_validation=0,
            source="binance_spot_rest",
            event_id="test-trade",
        )


def test_educational_and_programming_requests_never_fetch_market_data() -> None:
    async def run() -> None:
        market_data = FakeMarketData()
        orchestrator = BaymaxRequestOrchestrator(
            cast(BinanceMarketDataService, market_data),
            clock_health_provider=lambda: True,
        )
        educational = await orchestrator.prepare(
            AnalysisRequest(message="What is support and resistance?", intent="educational")
        )
        programming = await orchestrator.prepare(
            AnalysisRequest(message="Explain Python decorators", intent="programming")
        )
        assert educational.market_data_status == "not_required"
        assert programming.market_data_status == "not_required"
        assert market_data.calls == []

    asyncio.run(run())


def test_historical_request_does_not_use_current_price_service() -> None:
    async def run() -> None:
        market_data = FakeMarketData()
        orchestrator = BaymaxRequestOrchestrator(
            cast(BinanceMarketDataService, market_data),
            clock_health_provider=lambda: True,
        )
        result = await orchestrator.prepare(
            AnalysisRequest(
                message="Review BTCUSDT last month",
                intent="historical_market",
                symbol="BTCUSDT",
            )
        )
        assert result.market_data_status == "historical_not_implemented"
        assert market_data.calls == []

    asyncio.run(run())


def test_current_market_request_uses_normalized_symbol_and_verified_clock() -> None:
    async def run() -> None:
        market_data = FakeMarketData()
        orchestrator = BaymaxRequestOrchestrator(
            cast(BinanceMarketDataService, market_data),
            clock_health_provider=lambda: True,
        )
        result = await orchestrator.prepare(
            AnalysisRequest(
                message="What is BTC trading at now?",
                intent="current_market",
                symbol="btcusdt",
            )
        )
        assert market_data.calls == [("BTCUSDT", True)]
        assert result.market_data_required is True
        assert result.market_data_status == "ready"
        assert result.current_price is not None
        assert result.current_price.price == Decimal("95000.25")

    asyncio.run(run())


def test_unhealthy_clock_blocks_current_market_analysis() -> None:
    async def run() -> None:
        market_data = FakeMarketData()
        orchestrator = BaymaxRequestOrchestrator(
            cast(BinanceMarketDataService, market_data),
            clock_health_provider=lambda: False,
        )
        with pytest.raises(AnalysisInputUnavailable, match="unavailable"):
            await orchestrator.prepare(
                AnalysisRequest(
                    message="Analyze BTC now",
                    intent="current_market",
                    symbol="BTCUSDT",
                )
            )
        assert market_data.calls == [("BTCUSDT", False)]

    asyncio.run(run())


def test_current_market_request_requires_symbol() -> None:
    with pytest.raises(ValueError, match="symbol is required"):
        AnalysisRequest(message="BTC now", intent="current_market")


def test_analysis_prepare_endpoint_requires_owner_session() -> None:
    settings = Settings(
        app_env="test",
        log_level="INFO",
        cors_allowed_origins=("http://localhost:3000",),
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/analysis/prepare",
            json={
                "message": "What is BTC trading at now?",
                "intent": "current_market",
                "symbol": "BTCUSDT",
            },
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_market_data_service_is_started_and_closed_by_fastapi_lifespan() -> None:
    service = FakeMarketData()
    settings = Settings(
        app_env="test",
        log_level="INFO",
        cors_allowed_origins=("http://localhost:3000",),
    )
    with TestClient(
        create_app(
            settings,
            market_data_service_factory=lambda: cast(BinanceMarketDataService, service),
            clock_health_provider=lambda: True,
        )
    ) as client:
        assert service.started is True
        assert client.get("/api/v1/health").status_code == 200
    assert service.closed is True
