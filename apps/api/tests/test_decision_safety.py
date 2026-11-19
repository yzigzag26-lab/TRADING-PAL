from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal, cast
from uuid import UUID, uuid4

import pytest

from app.ai.classifier import BaymaxIntentClassifier, IntentClassification
from app.ai.engine import BaymaxAIEngine
from app.ai.generator import BaymaxAnalysisGenerator
from app.market_data.candles import HistoricalCandle, HistoricalCandleSeries
from app.market_data.decision_safety import (
    is_trading_decision_request,
    validate_historical_series_for_decision,
    validate_prepared_analysis_inputs,
)
from app.market_data.models import ValidatedPrice
from app.orchestration.requests import (
    AnalysisInputUnavailable,
    AnalysisRequest,
    BaymaxRequestOrchestrator,
    PreparedAnalysisInput,
)


def _price(
    now: datetime,
    *,
    event_age_ms: int = 0,
    symbol: str = "BTCUSDT",
    event_id: str | None = "123456",
) -> ValidatedPrice:
    event_time = now - timedelta(milliseconds=event_age_ms)
    received_time = now - timedelta(milliseconds=min(event_age_ms, 1))
    return ValidatedPrice(
        exchange="BINANCE",
        market="SPOT",
        symbol=symbol,
        price=Decimal("95000.25"),
        market_event_timestamp=event_time,
        received_timestamp=received_time,
        validated_timestamp=now,
        age_ms_at_validation=event_age_ms,
        source="binance_spot_rest",
        event_id=event_id,
    )


def _request(*, decision_requested: bool = False) -> AnalysisRequest:
    return AnalysisRequest(
        message="What is BTCUSDT trading at?",
        intent="current_market",
        symbol="BTCUSDT",
        decision_requested=decision_requested,
    )


def _prepared(price: ValidatedPrice, *, snapshot_id: UUID | None = None) -> PreparedAnalysisInput:
    return PreparedAnalysisInput(
        intent="current_market",
        market_data_required=True,
        market_data_status="ready",
        current_price=price,
        market_snapshot_id=snapshot_id if snapshot_id is not None else uuid4(),
    )


def test_final_gate_accepts_fresh_consistent_and_traceable_price_at_3000ms() -> None:
    now = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    validate_prepared_analysis_inputs(
        _request(),
        _prepared(_price(now, event_age_ms=3_000)),
        now=now,
    )


@pytest.mark.parametrize(
    ("event_age_ms", "message"),
    [
        (3_001, "expired"),
        (-1, "timestamps"),
    ],
)
def test_final_gate_rejects_stale_or_future_market_data(event_age_ms: int, message: str) -> None:
    now = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    price = _price(now, event_age_ms=max(event_age_ms, 0))
    if event_age_ms < 0:
        price = price.model_copy(
            update={"market_event_timestamp": now + timedelta(milliseconds=1)}
        )
    with pytest.raises(AnalysisInputUnavailable, match=message):
        validate_prepared_analysis_inputs(_request(), _prepared(price), now=now)


def test_final_gate_rejects_missing_snapshot_audit_identity() -> None:
    now = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    with pytest.raises(AnalysisInputUnavailable, match="provenance"):
        validate_prepared_analysis_inputs(
            _request(),
            PreparedAnalysisInput(
                intent="current_market",
                market_data_required=True,
                market_data_status="ready",
                current_price=_price(now),
                market_snapshot_id=None,
            ),
            now=now,
        )


def test_final_gate_rejects_conflicting_symbol_and_invalid_sequence_identity() -> None:
    now = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    with pytest.raises(AnalysisInputUnavailable, match="symbol"):
        validate_prepared_analysis_inputs(
            _request(),
            _prepared(_price(now, symbol="ETHUSDT")),
            now=now,
        )
    with pytest.raises(AnalysisInputUnavailable, match="sequence"):
        validate_prepared_analysis_inputs(
            _request(),
            _prepared(_price(now, event_id="not-a-trade-id")),
            now=now,
        )


def test_final_gate_rejects_timestamp_ordering_and_freshness_metadata_conflicts() -> None:
    now = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    future_received = _price(now).model_copy(
        update={"received_timestamp": now + timedelta(milliseconds=1)}
    )
    with pytest.raises(AnalysisInputUnavailable, match="timestamps"):
        validate_prepared_analysis_inputs(_request(), _prepared(future_received), now=now)

    false_age = _price(now).model_copy(update={"age_ms_at_validation": 25})
    with pytest.raises(AnalysisInputUnavailable, match="freshness"):
        validate_prepared_analysis_inputs(_request(), _prepared(false_age), now=now)


def test_historical_decision_gate_rejects_incomplete_series_and_unresolved_gaps() -> None:
    start = datetime(2026, 11, 19, 11, 0, tzinfo=UTC)
    series = HistoricalCandleSeries.model_construct(
        symbol="BTCUSDT",
        interval="1m",
        requested_start=start,
        requested_end=start,
        candles=(),
        missing_open_times=(start,),
        complete=False,
        recovery_attempts=2,
        source="binance_spot_rest",
        snapshot_id=uuid4(),
    )
    with pytest.raises(AnalysisInputUnavailable, match="incomplete"):
        validate_historical_series_for_decision(
            series,
            expected_symbol="BTCUSDT",
            now=start + timedelta(minutes=1),
        )


def test_historical_decision_gate_rejects_open_candles() -> None:
    start = datetime(2026, 11, 19, 11, 0, tzinfo=UTC)
    candle = HistoricalCandle.model_construct(
        exchange="BINANCE",
        market="SPOT",
        symbol="BTCUSDT",
        interval="1m",
        open_time=start,
        close_time=start + timedelta(seconds=59, milliseconds=999),
        open=Decimal("95000"),
        high=Decimal("95100"),
        low=Decimal("94900"),
        close=Decimal("95050"),
        base_volume=Decimal("10"),
        quote_volume=Decimal("950000"),
        trade_count=20,
        taker_buy_base_volume=Decimal("5"),
        taker_buy_quote_volume=Decimal("475000"),
        received_time=start + timedelta(minutes=1),
        is_closed=False,
    )
    series = HistoricalCandleSeries.model_construct(
        symbol="BTCUSDT",
        interval="1m",
        requested_start=start,
        requested_end=start,
        candles=(candle,),
        missing_open_times=(),
        complete=True,
        recovery_attempts=0,
        source="binance_spot_rest",
        snapshot_id=uuid4(),
    )
    with pytest.raises(AnalysisInputUnavailable, match="Open candles"):
        validate_historical_series_for_decision(
            series,
            expected_symbol="BTCUSDT",
            now=start + timedelta(minutes=2),
        )


class _Classifier:
    def __init__(
        self,
        *,
        decision_requested: bool = False,
        intent: Literal[
            "educational", "programming", "current_market", "historical_market"
        ] = "current_market",
    ) -> None:
        self.decision_requested = decision_requested
        self.intent = intent

    async def classify(self, message: str) -> IntentClassification:
        return IntentClassification(
            intent=self.intent,
            symbol="BTCUSDT" if self.intent == "current_market" else None,
            confidence=0.99,
            needs_clarification=False,
            decision_requested=self.decision_requested,
        )


class _Orchestrator:
    def __init__(self, prepared: PreparedAnalysisInput) -> None:
        self.prepared = prepared

    async def prepare(
        self, request: AnalysisRequest, *, request_id: UUID | None = None
    ) -> PreparedAnalysisInput:
        return self.prepared


class _Generator:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: AnalysisRequest, prepared: PreparedAnalysisInput) -> str:
        self.calls += 1
        return "generated"


def test_engine_rechecks_expiry_after_retrieval_and_never_calls_generator() -> None:
    now = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    price = _price(now - timedelta(milliseconds=1), event_age_ms=0)
    prepared = _prepared(price)
    generator = _Generator()
    engine = BaymaxAIEngine(
        classifier=cast(BaymaxIntentClassifier, _Classifier()),
        generator=cast(BaymaxAnalysisGenerator, generator),
        orchestrator=cast(BaymaxRequestOrchestrator, _Orchestrator(prepared)),
        decision_clock=lambda: now + timedelta(milliseconds=3_001),
    )
    with pytest.raises(AnalysisInputUnavailable, match="expired"):
        asyncio.run(engine.respond("What is BTCUSDT trading at?"))
    assert generator.calls == 0


def test_engine_blocks_explicit_trading_decision_before_generator() -> None:
    now = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    generator = _Generator()
    engine = BaymaxAIEngine(
        classifier=cast(BaymaxIntentClassifier, _Classifier()),
        generator=cast(BaymaxAnalysisGenerator, generator),
        orchestrator=cast(
            BaymaxRequestOrchestrator,
            _Orchestrator(
                PreparedAnalysisInput(
                intent="current_market",
                market_data_required=True,
                    market_data_status="decision_blocked",
                )
            ),
        ),
        decision_clock=lambda: now,
    )
    with pytest.raises(AnalysisInputUnavailable, match="trading recommendation"):
        asyncio.run(engine.respond("Should I buy BTCUSDT now?"))
    assert generator.calls == 0


def test_engine_keeps_educational_responses_available_without_market_data() -> None:
    generator = _Generator()
    engine = BaymaxAIEngine(
        classifier=cast(BaymaxIntentClassifier, _Classifier(intent="educational")),
        generator=cast(BaymaxAnalysisGenerator, generator),
        orchestrator=cast(BaymaxRequestOrchestrator, _Orchestrator(
            PreparedAnalysisInput(
                intent="educational",
                market_data_required=False,
                    market_data_status="not_required",
                )
            ),
        ),
    )
    result = asyncio.run(engine.respond("Explain support and resistance."))
    assert result.answer == "generated"
    assert generator.calls == 1


def test_deterministic_detector_flags_explicit_recommendation_language() -> None:
    assert is_trading_decision_request("Should I buy BTCUSDT now?", intent="current_market")
    assert is_trading_decision_request("Give me a trading signal", intent="current_market")
    assert not is_trading_decision_request("Explain what buy means", intent="educational")
    assert is_trading_decision_request("Should I buy BTCUSDT?", intent="educational")
