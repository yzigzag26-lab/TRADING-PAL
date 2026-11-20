"""Engine-level remediation tests: release-time freshness, Groq proposal
validation, and Gate 3 safety integration (findings F1/F2/F4)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import uuid4

import pytest

from app.ai.assessment import MarketAssessment
from app.ai.classifier import BaymaxIntentClassifier
from app.ai.engine import BaymaxAIEngine
from app.ai.generator import AnalysisGenerationError, BaymaxAnalysisGenerator
from app.intelligence.analyzer import (
    MarketIntelligenceEngine,
    MarketIntelligenceInput,
)
from app.intelligence.schemas import MarketIntelligenceReport
from app.market_data.analysis_input import MarketIntelligenceInputBuilder
from app.market_data.freshness import MarketDataUnavailable
from app.market_data.models import ValidatedPrice
from app.market_data.provenance import PriceSnapshotRecorder
from app.market_data.service import BinanceMarketDataService
from app.orchestration.requests import (
    AnalysisInputUnavailable,
    AnalysisRequest,
    BaymaxRequestOrchestrator,
)
from app.strategy.decision_safety import DecisionSafetyGate
from tests import test_strategy as ts


class FakeGroq:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses

    async def complete(self, **kwargs: object) -> str:
        return self.responses.pop(0)


class FakeMarketData:
    def __init__(self, price: ValidatedPrice | None = None) -> None:
        self.price = price

    async def get_current_price(self, symbol: str, *, clock_healthy: bool) -> ValidatedPrice:
        if not clock_healthy or self.price is None:
            raise MarketDataUnavailable("unavailable")
        return self.price


class FakeProvenance:
    def record_price(self, price: ValidatedPrice, *, request_id: object = None) -> object:
        return uuid4()


class FakeBuilder:
    def __init__(self, bundle: MarketIntelligenceInput) -> None:
        self.bundle = bundle
        self.calls = 0

    async def build(self, prepared: object, **kwargs: object) -> MarketIntelligenceInput:
        self.calls += 1
        return self.bundle


class FakeIntelligenceEngine:
    def __init__(self, report: MarketIntelligenceReport) -> None:
        self.report = report

    def analyze(
        self, bundle: MarketIntelligenceInput, **kwargs: object
    ) -> MarketIntelligenceReport:
        return self.report


class FakeGenerator:
    """Returns a canned Groq proposal or simulates provider failure."""

    def __init__(self, proposal: str | None = "WAIT", *, fail: bool = False) -> None:
        self.proposal = proposal
        self.fail = fail
        self.contexts: list[dict[str, object]] = []

    async def generate_assessment(
        self, request: AnalysisRequest, context: Mapping[str, object]
    ) -> MarketAssessment:
        self.contexts.append(dict(context))
        if self.fail or self.proposal is None:
            raise AnalysisGenerationError("provider down")
        return MarketAssessment(
            decision=self.proposal,  # type: ignore[arg-type]
            summary=f"Model proposal: {self.proposal}",
        )


def _price() -> ValidatedPrice:
    now = datetime.now(UTC)
    return ValidatedPrice(
        exchange="BINANCE",
        market="SPOT",
        symbol="BTCUSDT",
        price=Decimal("100.00"),
        market_event_timestamp=now,
        received_timestamp=now,
        validated_timestamp=now,
        age_ms_at_validation=0,
        source="binance_spot_rest",
        event_id="12345",
    )


def _engine(
    *,
    report: MarketIntelligenceReport,
    proposal: str | None = "WAIT",
    fail: bool = False,
    decision_clock: Callable[[], datetime] | None = None,
    allow_decisions: bool = True,
) -> tuple[BaymaxAIEngine, FakeBuilder, FakeGenerator]:
    price = _price()
    bundle = MarketIntelligenceInput(
        price=price,
        price_snapshot_id=uuid4(),
        timeframes={},
    )
    builder = FakeBuilder(bundle)
    generator = FakeGenerator(proposal, fail=fail)
    market_data = FakeMarketData(price)
    engine = BaymaxAIEngine(
        classifier=BaymaxIntentClassifier(
            cast(object, FakeGroq([_classification_json()]))  # type: ignore[arg-type]
        ),
        generator=cast(BaymaxAnalysisGenerator, generator),
        orchestrator=BaymaxRequestOrchestrator(
            cast(BinanceMarketDataService, market_data),
            clock_health_provider=lambda: True,
            provenance_repository=cast(PriceSnapshotRecorder, FakeProvenance()),
            allow_trading_decisions=allow_decisions,
        ),
        intelligence_builder=cast(MarketIntelligenceInputBuilder, builder),
        intelligence_engine=cast(MarketIntelligenceEngine, FakeIntelligenceEngine(report)),
        safety_gate=DecisionSafetyGate(),
        decision_clock=decision_clock or (lambda: datetime.now(UTC)),
    )
    return engine, builder, generator


def _classification_json() -> str:
    return (
        '{"intent":"current_market","symbol":"BTCUSDT","confidence":0.99,'
        '"needs_clarification":false,"decision_requested":true}'
    )


def test_groq_buy_proposal_confirmed_by_safety() -> None:
    async def run() -> None:
        report = ts._report(ts.BULLISH_5, zones_1h=ts.BUY_ZONES)
        engine, _, _ = _engine(report=report, proposal="BUY")
        result = await engine.respond("Should I buy BTCUSDT?")
        assert result.assessment is not None
        assert result.assessment.decision == "BUY"
        assert result.assessment.model_decision == "BUY"
        assert result.assessment.scenario is not None
        assert result.assessment.intelligence is not None
        assert len(result.assessment.intelligence.timeframes) == 5

    asyncio.run(run())


def test_groq_sell_proposal_yields_spot_exit_guidance() -> None:
    async def run() -> None:
        zones = (
            ts._zone("support", "90.00", "91.00"),
            ts._zone("resistance", "104.00", "105.00"),
        )
        report = ts._report(ts.BEARISH_5, zones_1h=zones)
        engine, _, _ = _engine(report=report, proposal="SELL")
        result = await engine.respond("Should I sell BTCUSDT?")
        assert result.assessment is not None
        assert result.assessment.decision == "SELL"
        assert result.assessment.exit_guidance is not None
        assert result.assessment.scenario is None

    asyncio.run(run())


def test_groq_wait_proposal_returns_wait() -> None:
    async def run() -> None:
        report = ts._report(ts.BULLISH_5, zones_1h=ts.BUY_ZONES)
        engine, _, _ = _engine(report=report, proposal="WAIT")
        result = await engine.respond("Analyse BTCUSDT")
        assert result.assessment is not None
        assert result.assessment.decision == "WAIT"
        assert result.assessment.scenario is None

    asyncio.run(run())


def test_safety_vetoes_groq_buy_on_conflicting_evidence() -> None:
    """F4: Groq proposes BUY but Python evidence says WAIT -> forced WAIT."""

    async def run() -> None:
        report = ts._report(
            {"5m": "bullish", "15m": "bullish", "1h": "bearish", "4h": "bearish", "1d": "bearish"},
            alignment_status="conflicting",
        )
        engine, _, _ = _engine(report=report, proposal="BUY")
        result = await engine.respond("Should I buy BTCUSDT?")
        assert result.assessment is not None
        assert result.assessment.decision == "WAIT"
        assert result.assessment.model_decision == "BUY"
        assert result.assessment.scenario is None
        assert any("Model proposed BUY" in item for item in result.assessment.limitations)

    asyncio.run(run())


def test_groq_unavailable_returns_deterministic_wait() -> None:
    async def run() -> None:
        report = ts._report(ts.BULLISH_5, zones_1h=ts.BUY_ZONES)
        engine, _, _ = _engine(report=report, fail=True)
        result = await engine.respond("Should I buy BTCUSDT?")
        assert result.assessment is not None
        assert result.assessment.decision == "WAIT"
        assert result.assessment.model_decision is None

    asyncio.run(run())


def test_release_time_freshness_vetoes_stale_price() -> None:
    """F1: price ages past 3s during analysis -> final assessment is WAIT."""

    async def run() -> None:
        report = ts._report(ts.BULLISH_5, zones_1h=ts.BUY_ZONES)
        stale_clock = lambda: datetime.now(UTC) + timedelta(seconds=10)  # noqa: E731
        engine, _, _ = _engine(report=report, proposal="BUY", decision_clock=stale_clock)
        result = await engine.respond("Should I buy BTCUSDT?")
        assert result.assessment is not None
        assert result.assessment.decision == "WAIT"
        assert result.assessment.model_decision == "BUY"

    asyncio.run(run())


def test_gate3_block_preserved_without_decision_evidence() -> None:
    """F2: without the Gate 4 evidence path, decision requests stay blocked."""

    async def run() -> None:
        report = ts._report(ts.BULLISH_5, zones_1h=ts.BUY_ZONES)
        engine, builder, _ = _engine(report=report, allow_decisions=False)
        with pytest.raises(AnalysisInputUnavailable):
            await engine.respond("Should I buy BTCUSDT?")
        assert builder.calls == 0

    asyncio.run(run())


def test_groq_numeric_claim_not_present_in_verified_context_is_rejected() -> None:
    async def run() -> None:
        client = FakeGroq(
            [
                '{"decision":"BUY","summary":"RSI is 99.0 and momentum is strong.",'
                '"key_evidence":["Trend is bullish"],"risks":[],"invalidation_conditions":[],'
                '"limitations":[]}'
            ]
        )
        generator = BaymaxAnalysisGenerator(client)
        request = AnalysisRequest(
            message="Analyse BTCUSDT",
            intent="current_market",
            symbol="BTCUSDT",
            decision_requested=True,
        )
        context = {"current_price": "100.00", "indicators": {"rsi14": 52.3}}
        with pytest.raises(AnalysisGenerationError, match="numerical claims"):
            await generator.generate_assessment(request, context)

    asyncio.run(run())


def test_groq_assessment_accepts_non_numeric_explanation_with_numeric_context() -> None:
    async def run() -> None:
        client = FakeGroq(
            [
                '{"decision":"BUY","summary":"The verified momentum evidence supports a bullish proposal.",'
                '"key_evidence":["Momentum and trend evidence align."],"risks":["Volatility remains a risk."],'
                '"invalidation_conditions":["A confirmed trend reversal."],"limitations":[]}'
            ]
        )
        generator = BaymaxAnalysisGenerator(client)
        request = AnalysisRequest(
            message="Analyse BTCUSDT",
            intent="current_market",
            symbol="BTCUSDT",
            decision_requested=True,
        )
        context = {"current_price": "100.00", "indicators": {"rsi14": 52.3}}
        result = await generator.generate_assessment(request, context)
        assert result.decision == "BUY"
        assert "verified momentum" in result.summary.lower()

    asyncio.run(run())


def test_groq_cannot_supply_or_override_python_scenario_levels() -> None:
    async def run() -> None:
        client = FakeGroq(
            [
                '{"decision":"BUY","summary":"Bullish evidence supports the proposal.",'
                '"key_evidence":[],"risks":[],"invalidation_conditions":[],"limitations":[],'
                '"entry":99999,"stop_loss":1}'
            ]
        )
        generator = BaymaxAnalysisGenerator(client)
        request = AnalysisRequest(
            message="Analyse BTCUSDT",
            intent="current_market",
            symbol="BTCUSDT",
            decision_requested=True,
        )
        with pytest.raises(AnalysisGenerationError):
            await generator.generate_assessment(request, {"current_price": "100.00"})

    asyncio.run(run())


def test_gate4_pipeline_emits_stage_latency_and_freshness_metrics(caplog: pytest.LogCaptureFixture) -> None:
    async def run() -> None:
        report = ts._report(ts.BULLISH_5, zones_1h=ts.BUY_ZONES)
        engine, _, _ = _engine(report=report, proposal="BUY")
        with caplog.at_level(logging.INFO, logger="app.ai.engine"):
            result = await engine.respond("Should I buy BTCUSDT?")
        assert result.assessment is not None
        record = next(item for item in caplog.records if item.message == "Gate 4 analysis timing")
        assert record.gate4_historical_fetch_ms == 0.0
        assert record.gate4_indicator_analysis_ms >= 0
        assert record.gate4_groq_proposal_ms >= 0
        assert record.gate4_decision_safety_ms >= 0
        assert record.gate4_total_ms >= 0
        assert record.gate4_freshness_veto is False

    asyncio.run(run())


def test_groq_numeric_claim_is_rejected_even_when_number_exists_in_context() -> None:
    async def run() -> None:
        client = FakeGroq(
            [
                '{"decision":"BUY","summary":"RSI is 52.3.",'
                '"key_evidence":[],"risks":[],"invalidation_conditions":[],"limitations":[]}'
            ]
        )
        generator = BaymaxAnalysisGenerator(client)
        request = AnalysisRequest(
            message="Analyse BTCUSDT",
            intent="current_market",
            symbol="BTCUSDT",
            decision_requested=True,
        )
        with pytest.raises(AnalysisGenerationError, match="numerical claims"):
            await generator.generate_assessment(
                request, {"current_price": "100.00", "indicators": {"rsi14": 52.3}}
            )

    asyncio.run(run())
