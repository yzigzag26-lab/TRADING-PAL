from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import pytest

from app.ai.classifier import BaymaxIntentClassifier
from app.ai.engine import BaymaxAIEngine
from app.ai.generator import BaymaxAnalysisGenerator
from app.ai.groq import GroqChatClient, GroqUnavailable
from app.market_data.freshness import MarketDataUnavailable
from app.market_data.models import ValidatedPrice
from app.market_data.service import BinanceMarketDataService
from app.orchestration.requests import AnalysisInputUnavailable, BaymaxRequestOrchestrator


class FakeGroq:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    async def complete(
        self,
        *,
        messages: list[dict[str, str]],
        response_format: dict[str, object] | None = None,
        max_tokens: int = 1200,
        temperature: float = 0.2,
    ) -> str:
        self.calls.append(
            {
                "messages": messages,
                "response_format": response_format,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        return self.responses.pop(0)


class FakeMarketData:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.calls: list[tuple[str, bool]] = []

    async def get_current_price(self, symbol: str, *, clock_healthy: bool) -> ValidatedPrice:
        self.calls.append((symbol, clock_healthy))
        if not self.available or not clock_healthy:
            raise MarketDataUnavailable("unavailable")
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


def test_educational_request_runs_classifier_and_generator_without_market_data() -> None:
    async def run() -> None:
        groq = FakeGroq(
            [
                '{"intent":"educational","symbol":null,"confidence":0.99,'
                '"needs_clarification":false}',
                "## What is support?\\n"
                "Support is a price area where demand has historically appeared.",
            ]
        )
        market_data = FakeMarketData()
        engine = BaymaxAIEngine(
            classifier=BaymaxIntentClassifier(groq),
            generator=BaymaxAnalysisGenerator(groq),
            orchestrator=BaymaxRequestOrchestrator(
                cast(BinanceMarketDataService, market_data),
                clock_health_provider=lambda: True,
            ),
        )
        result = await engine.respond("Explain support levels.")
        assert result.intent == "educational"
        assert result.market_data_status == "not_required"
        assert result.needs_clarification is False
        assert "What is support" in result.answer
        assert market_data.calls == []
        assert groq.calls[0]["response_format"] is not None

    asyncio.run(run())


def test_current_market_request_fails_closed_before_analysis_generation() -> None:
    async def run() -> None:
        groq = FakeGroq(
            [
                '{"intent":"current_market","symbol":"BTCUSDT","confidence":0.98,'
                '"needs_clarification":false}'
            ]
        )
        market_data = FakeMarketData(available=False)
        engine = BaymaxAIEngine(
            classifier=BaymaxIntentClassifier(groq),
            generator=BaymaxAnalysisGenerator(groq),
            orchestrator=BaymaxRequestOrchestrator(
                cast(BinanceMarketDataService, market_data),
                clock_health_provider=lambda: True,
            ),
        )
        with pytest.raises(AnalysisInputUnavailable, match="unavailable"):
            await engine.respond("What is BTCUSDT trading at right now?")
        assert market_data.calls == [("BTCUSDT", True)]
        assert len(groq.calls) == 1

    asyncio.run(run())


def test_low_confidence_classification_requests_clarification_without_fetching() -> None:
    async def run() -> None:
        groq = FakeGroq(
            [
                '{"intent":"current_market","symbol":null,"confidence":0.35,'
                '"needs_clarification":false}'
            ]
        )
        market_data = FakeMarketData()
        engine = BaymaxAIEngine(
            classifier=BaymaxIntentClassifier(groq),
            generator=BaymaxAnalysisGenerator(groq),
            orchestrator=BaymaxRequestOrchestrator(
                cast(BinanceMarketDataService, market_data),
                clock_health_provider=lambda: True,
            ),
        )
        result = await engine.respond("What about the market?")
        assert result.needs_clarification is True
        assert result.market_data_status == "not_requested"
        assert market_data.calls == []
        assert len(groq.calls) == 1

    asyncio.run(run())


def test_historical_request_is_explicitly_not_implemented_in_generation_context() -> None:
    async def run() -> None:
        groq = FakeGroq(
            [
                '{"intent":"historical_market","symbol":"BTCUSDT","confidence":0.95,'
                '"needs_clarification":false}',
                "Historical market retrieval is not implemented yet.",
            ]
        )
        market_data = FakeMarketData()
        engine = BaymaxAIEngine(
            classifier=BaymaxIntentClassifier(groq),
            generator=BaymaxAnalysisGenerator(groq),
            orchestrator=BaymaxRequestOrchestrator(
                cast(BinanceMarketDataService, market_data),
                clock_health_provider=lambda: True,
            ),
        )
        result = await engine.respond("Review BTCUSDT over the previous month.")
        assert result.market_data_status == "historical_not_implemented"
        assert "not implemented" in result.answer
        assert market_data.calls == []
        assert len(groq.calls) == 2

    asyncio.run(run())


def test_groq_client_reports_missing_api_key_without_network_access() -> None:
    async def run() -> None:
        client = GroqChatClient(api_key=None)
        with pytest.raises(GroqUnavailable, match="not configured"):
            await client.complete(messages=[{"role": "user", "content": "Hello"}])

    asyncio.run(run())
