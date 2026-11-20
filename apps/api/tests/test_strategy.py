"""Deterministic tests for setup/scenario calculation and decision safety."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.intelligence.schemas import (
    IndicatorReading,
    MarketIntelligenceReport,
    PriceZone,
    TimeframeAlignment,
    TimeframeAnalysis,
    TrendAssessment,
    VolatilityAssessment,
)
from app.market_data.models import ValidatedPrice
from app.orchestration.requests import AnalysisRequest, PreparedAnalysisInput
from app.strategy.decision_safety import DecisionSafetyGate
from app.strategy.schemas import SafetyResult, StrategyOutcome
from app.strategy.setup import evaluate_setup

NOW = datetime(2026, 2, 1, tzinfo=UTC)
PRICE = Decimal("100.00")


def _atr_reading(value: float = 2.0) -> IndicatorReading:
    return IndicatorReading(
        name="ATR",
        parameters={"period": 14},
        values={"value": value, "percent": value},
        candle_count=300,
        warmup_candles=15,
        sufficient_history=True,
        latest_input_open_time=NOW,
        calculated_at=NOW,
    )


def _zone(side: str, lower: str, upper: str, *, active: bool = True) -> PriceZone:
    return PriceZone(
        side=side,  # type: ignore[arg-type]
        lower=Decimal(lower),
        upper=Decimal(upper),
        timeframe="1h",
        method="swing_cluster_v1",
        touches=3,
        strength=0.6,
        active=active,
        source_open_times=(NOW,),
    )


def _tf(
    interval: str,
    direction: str,
    *,
    zones: tuple[PriceZone, ...] = (),
    atr: float = 2.0,
    vol_level: str = "normal",
    vol_direction: str = "stable",
    usable: bool = True,
) -> TimeframeAnalysis:
    return TimeframeAnalysis(
        interval=interval,
        symbol="BTCUSDT",
        snapshot_id=uuid4(),
        candle_count=300,
        closed_candle_count=300,
        series_complete=True,
        last_closed_open_time=NOW,
        last_closed_close=Decimal("100"),
        indicators=(_atr_reading(atr),),
        trend=TrendAssessment(direction=direction, score=0.5),  # type: ignore[arg-type]
        zones=zones,
        volatility=VolatilityAssessment(
            level=vol_level,  # type: ignore[arg-type]
            direction=vol_direction,  # type: ignore[arg-type]
            atr_percent=2.0,
        ),
        usable=usable,
        limitations=(),
    )


def _report(
    directions: dict[str, str],
    *,
    zones_1h: tuple[PriceZone, ...] = (),
    data_quality: str = "complete",
    readiness: str = "ready",
    alignment_status: str | None = None,
) -> MarketIntelligenceReport:
    bullish = sum(1 for d in directions.values() if d == "bullish")
    bearish = sum(1 for d in directions.values() if d == "bearish")
    total = len(directions)
    if alignment_status is None:
        if bullish == total:
            alignment_status = "aligned_bullish"
        elif bearish == total:
            alignment_status = "aligned_bearish"
        elif bullish and bearish:
            alignment_status = "conflicting"
        else:
            alignment_status = "partial"
    analyses = tuple(
        _tf(
            interval,
            direction,
            zones=zones_1h if interval == "1h" else (),
        )
        for interval, direction in directions.items()
    )
    return MarketIntelligenceReport(
        symbol="BTCUSDT",
        analyzed_at=NOW,
        current_price=str(PRICE),
        current_price_snapshot_id=uuid4(),
        timeframe_analyses=analyses,
        alignment=TimeframeAlignment(
            status=alignment_status,  # type: ignore[arg-type]
            directions=dict(directions),  # type: ignore[arg-type]
        ),
        data_quality=data_quality,  # type: ignore[arg-type]
        readiness=readiness,  # type: ignore[arg-type]
    )


def _validated_price(*, age_ms: int = 10) -> ValidatedPrice:
    market_time = NOW - timedelta(milliseconds=age_ms)
    return ValidatedPrice(
        exchange="BINANCE",
        market="SPOT",
        symbol="BTCUSDT",
        price=PRICE,
        market_event_timestamp=market_time,
        received_timestamp=NOW,
        validated_timestamp=NOW,
        age_ms_at_validation=age_ms,
        source="binance_spot_rest",
        event_id="1001",
    )


def _request() -> AnalysisRequest:
    return AnalysisRequest(
        message="Should I buy BTCUSDT?",
        intent="current_market",
        symbol="BTCUSDT",
        decision_requested=True,
    )


def _prepared(price: ValidatedPrice | None = None) -> PreparedAnalysisInput:
    return PreparedAnalysisInput(
        intent="current_market",
        market_data_required=True,
        market_data_status="ready",
        current_price=price or _validated_price(),
        market_snapshot_id=uuid4(),
    )


def _gate(
    report: MarketIntelligenceReport,
    candidate: StrategyOutcome,
    proposal: str | None = "BUY",
    *,
    now: datetime = NOW,
    price: ValidatedPrice | None = None,
    gate: DecisionSafetyGate | None = None,
) -> SafetyResult:
    return (gate or DecisionSafetyGate()).evaluate(
        report,
        candidate,
        proposal,
        request=_request(),
        prepared=_prepared(price),
        now=now,
    )


BULLISH_5 = {"5m": "bullish", "15m": "bullish", "1h": "bullish", "4h": "bullish", "1d": "bullish"}
BEARISH_5 = {"5m": "bearish", "15m": "bearish", "1h": "bearish", "4h": "bearish", "1d": "bearish"}
BUY_ZONES = (
    _zone("support", "95.00", "96.00"),
    _zone("resistance", "110.00", "111.00"),
    _zone("resistance", "120.00", "121.00"),
)


def test_wait_when_alignment_conflicting() -> None:
    report = _report(
        {"5m": "bullish", "15m": "bullish", "1h": "bearish", "4h": "bearish", "1d": "bearish"},
        alignment_status="conflicting",
    )
    outcome = evaluate_setup(report)
    assert outcome.proposed_decision == "WAIT"
    assert outcome.scenario is None
    assert outcome.blocking_reasons


def test_wait_when_data_insufficient() -> None:
    report = _report(
        {"5m": "bullish"},
        data_quality="insufficient",
        readiness="blocked",
        alignment_status="insufficient",
    )
    outcome = evaluate_setup(report)
    assert outcome.proposed_decision == "WAIT"


def test_buy_scenario_levels_are_deterministic() -> None:
    report = _report(BULLISH_5, zones_1h=BUY_ZONES)
    outcome = evaluate_setup(report)
    assert outcome.proposed_decision == "BUY"
    scenario = outcome.scenario
    assert scenario is not None
    assert scenario.entry_zone.lower == Decimal("99.80")
    assert scenario.entry_zone.upper == Decimal("100.20")
    assert scenario.stop_loss.price == Decimal("94.50")
    assert scenario.take_profit_1.price == Decimal("110.00")
    assert scenario.take_profit_2 is not None
    assert scenario.take_profit_2.price == Decimal("120.00")
    assert scenario.risk_reward_ratio == Decimal("1.82")


def test_wait_when_risk_reward_too_low() -> None:
    zones = (
        _zone("support", "98.00", "99.00"),
        _zone("resistance", "101.00", "102.00"),
    )
    report = _report(BULLISH_5, zones_1h=zones)
    outcome = evaluate_setup(report)
    assert outcome.proposed_decision == "WAIT"
    assert any("Risk/reward" in reason for reason in outcome.blocking_reasons)


def test_wait_when_no_target_zone() -> None:
    zones = (_zone("support", "95.00", "96.00"),)
    report = _report(BULLISH_5, zones_1h=zones)
    outcome = evaluate_setup(report)
    assert outcome.proposed_decision == "WAIT"


def test_sell_produces_spot_exit_guidance_not_short_scenario() -> None:
    """F3: bearish alignment yields exit guidance, never a short scenario."""
    zones = (
        _zone("support", "90.00", "91.00"),
        _zone("resistance", "104.00", "105.00"),
    )
    report = _report(BEARISH_5, zones_1h=zones)
    outcome = evaluate_setup(report)
    assert outcome.proposed_decision == "SELL"
    assert outcome.scenario is None
    guidance = outcome.exit_guidance
    assert guidance is not None
    assert guidance.kind == "spot_exit"
    assert "not a short" in guidance.note
    assert guidance.trim_levels  # resistance zones above price
    assert guidance.breakdown_exit is not None
    assert guidance.breakdown_exit.price == Decimal("90.00")


def test_sell_waits_without_any_zone_anchor() -> None:
    report = _report(BEARISH_5, zones_1h=())
    outcome = evaluate_setup(report)
    assert outcome.proposed_decision == "WAIT"
    assert outcome.exit_guidance is None


def test_high_expanding_volatility_blocks_setup() -> None:
    report = _report(BULLISH_5, zones_1h=BUY_ZONES)
    analyses = []
    for item in report.timeframe_analyses:
        if item.interval == "1h":
            item = item.model_copy(
                update={
                    "volatility": VolatilityAssessment(
                        level="high", direction="expanding", atr_percent=5.0
                    )
                }
            )
        analyses.append(item)
    report = report.model_copy(update={"timeframe_analyses": tuple(analyses)})
    outcome = evaluate_setup(report)
    assert outcome.proposed_decision == "WAIT"
    assert any("Volatility" in r for r in outcome.blocking_reasons)


def test_safety_gate_confirms_valid_buy_proposal() -> None:
    report = _report(BULLISH_5, zones_1h=BUY_ZONES)
    candidate = evaluate_setup(report)
    result = _gate(report, candidate, proposal="BUY")
    assert result.decision == "BUY"
    assert result.scenario is not None
    assert not result.blocked
    assert result.model_proposal == "BUY"


def test_safety_gate_vetoes_buy_when_price_stale_at_release() -> None:
    """F1: price fresh at validation but stale at release time -> WAIT."""
    report = _report(BULLISH_5, zones_1h=BUY_ZONES)
    candidate = evaluate_setup(report)
    # Price validated 10ms ago; release happens 4s later.
    result = _gate(
        report,
        candidate,
        proposal="BUY",
        now=NOW + timedelta(seconds=4),
    )
    assert result.decision == "WAIT"
    assert result.blocked
    assert any("expired" in r for r in result.block_reasons)


def test_safety_gate_allows_buy_when_price_fresh_at_release() -> None:
    report = _report(BULLISH_5, zones_1h=BUY_ZONES)
    candidate = evaluate_setup(report)
    result = _gate(
        report,
        candidate,
        proposal="BUY",
        now=NOW + timedelta(milliseconds=500),
    )
    assert result.decision == "BUY"


def test_safety_gate_vetoes_proposal_on_conflicting_alignment() -> None:
    report = _report(
        {"5m": "bullish", "15m": "bullish", "1h": "bearish", "4h": "bearish", "1d": "bearish"},
        zones_1h=BUY_ZONES,
        alignment_status="conflicting",
    )
    candidate = evaluate_setup(report)
    result = _gate(report, candidate, proposal="BUY")
    assert result.decision == "WAIT"
    assert any("conflicting" in r.lower() for r in result.block_reasons)


def test_safety_gate_forces_wait_when_model_unavailable() -> None:
    report = _report(BULLISH_5, zones_1h=BUY_ZONES)
    candidate = evaluate_setup(report)
    result = _gate(report, candidate, proposal=None)
    assert result.decision == "WAIT"
    assert result.model_proposal is None


def test_safety_gate_rejects_model_buy_when_candidate_is_wait() -> None:
    report = _report(
        {"5m": "bullish", "15m": "bullish", "1h": "bearish", "4h": "bearish", "1d": "bearish"},
        alignment_status="conflicting",
    )
    candidate = evaluate_setup(report)
    assert candidate.proposed_decision == "WAIT"
    result = _gate(report, candidate, proposal="BUY")
    assert result.decision == "WAIT"
    assert result.checks and "model_proposal_vetoed_by_safety" in result.checks


def test_safety_gate_accepts_wait_proposal() -> None:
    report = _report(BULLISH_5, zones_1h=BUY_ZONES)
    candidate = evaluate_setup(report)
    result = _gate(report, candidate, proposal="WAIT")
    assert result.decision == "WAIT"
    assert result.scenario is None
    assert not result.blocked


def test_safety_gate_confirms_sell_proposal_with_exit_guidance() -> None:
    zones = (
        _zone("support", "90.00", "91.00"),
        _zone("resistance", "104.00", "105.00"),
    )
    report = _report(BEARISH_5, zones_1h=zones)
    candidate = evaluate_setup(report)
    result = _gate(report, candidate, proposal="SELL")
    assert result.decision == "SELL"
    assert result.exit_guidance is not None
    assert result.scenario is None


def test_safety_gate_blocks_on_incomplete_series() -> None:
    report = _report(BULLISH_5, zones_1h=BUY_ZONES)
    analyses = [
        item.model_copy(update={"series_complete": False}) if item.interval == "4h" else item
        for item in report.timeframe_analyses
    ]
    report = report.model_copy(update={"timeframe_analyses": tuple(analyses)})
    candidate = evaluate_setup(report)
    result = _gate(report, candidate, proposal="BUY")
    assert result.decision == "WAIT"
    assert any("Incomplete" in r for r in result.block_reasons)


def test_safety_gate_blocks_on_missing_timeframe() -> None:
    report = _report({"1h": "bullish"}, alignment_status="insufficient")
    candidate = evaluate_setup(report)
    result = _gate(report, candidate, proposal="BUY")
    assert result.decision == "WAIT"
    assert any("Missing timeframe" in r for r in result.block_reasons)


def test_safety_gate_blocks_on_symbol_mismatch() -> None:
    report = _report(BULLISH_5, zones_1h=BUY_ZONES)
    candidate = evaluate_setup(report)
    bad_price = _validated_price().model_copy(update={"symbol": "ETHUSDT"})
    result = _gate(report, candidate, proposal="BUY", price=bad_price)
    assert result.decision == "WAIT"
    assert any("symbol" in r.lower() or "Market symbol" in r for r in result.block_reasons)


def test_safety_gate_blocks_on_non_decimal_event_id() -> None:
    report = _report(BULLISH_5, zones_1h=BUY_ZONES)
    candidate = evaluate_setup(report)
    bad_price = _validated_price().model_copy(update={"event_id": "t1"})
    result = _gate(report, candidate, proposal="BUY", price=bad_price)
    assert result.decision == "WAIT"
    assert any("event" in r.lower() for r in result.block_reasons)


def test_safety_gate_requires_provenance_when_configured() -> None:
    report = _report(BULLISH_5, zones_1h=BUY_ZONES)
    analyses = [item.model_copy(update={"snapshot_id": None}) for item in report.timeframe_analyses]
    report = report.model_copy(
        update={
            "timeframe_analyses": tuple(analyses),
            "current_price_snapshot_id": None,
        }
    )
    candidate = evaluate_setup(report)
    result = _gate(
        report, candidate, proposal="BUY", gate=DecisionSafetyGate(require_provenance=True)
    )
    assert result.decision == "WAIT"
    assert any("provenance" in r.lower() for r in result.block_reasons)


def test_buy_waits_when_all_support_zones_are_above_current_price() -> None:
    zones = (
        _zone("support", "102.00", "103.00"),
        _zone("resistance", "110.00", "111.00"),
    )
    outcome = evaluate_setup(_report(BULLISH_5, zones_1h=zones))
    assert outcome.proposed_decision == "WAIT"
    assert outcome.scenario is None
    assert any("No active support zone" in reason for reason in outcome.blocking_reasons)


def test_buy_accepts_support_zone_containing_current_price() -> None:
    zones = (
        _zone("support", "99.00", "101.00"),
        _zone("resistance", "110.00", "111.00"),
    )
    outcome = evaluate_setup(_report(BULLISH_5, zones_1h=zones))
    assert outcome.proposed_decision == "BUY"
    assert outcome.scenario is not None
    assert outcome.scenario.stop_loss.price < outcome.scenario.entry_zone.lower


def test_buy_accepts_support_zone_below_current_price() -> None:
    outcome = evaluate_setup(_report(BULLISH_5, zones_1h=BUY_ZONES))
    assert outcome.proposed_decision == "BUY"
    assert outcome.scenario is not None
    assert outcome.scenario.stop_loss.price < outcome.scenario.entry_zone.lower


def test_buy_waits_when_no_support_zones_exist() -> None:
    zones = (_zone("resistance", "110.00", "111.00"),)
    outcome = evaluate_setup(_report(BULLISH_5, zones_1h=zones))
    assert outcome.proposed_decision == "WAIT"
    assert outcome.scenario is None
    assert any("No active support zone" in reason for reason in outcome.blocking_reasons)


def test_buy_uses_below_price_support_not_overhead_support() -> None:
    zones = (
        _zone("support", "95.00", "96.00"),
        _zone("support", "102.00", "103.00"),
        _zone("resistance", "110.00", "111.00"),
    )
    outcome = evaluate_setup(_report(BULLISH_5, zones_1h=zones))
    assert outcome.proposed_decision == "BUY"
    assert outcome.scenario is not None
    assert outcome.scenario.stop_loss.price == Decimal("94.50")
    assert outcome.scenario.stop_loss.price < outcome.scenario.entry_zone.lower
    assert outcome.scenario.take_profit_1.price > PRICE


def test_safety_gate_requires_all_five_timeframes_to_be_usable() -> None:
    report = _report(BULLISH_5, zones_1h=BUY_ZONES)
    analyses = [
        item.model_copy(
            update={
                "usable": False,
                "limitations": ("Only 45 closed candles; minimum is 60",),
            }
        )
        if item.interval == "1d"
        else item
        for item in report.timeframe_analyses
    ]
    report = report.model_copy(update={"timeframe_analyses": tuple(analyses)})
    candidate = evaluate_setup(report)
    result = _gate(report, candidate, proposal="BUY")
    assert result.decision == "WAIT"
    assert any("Only 4 usable timeframe(s); minimum is 5" in reason for reason in result.block_reasons)
    assert any("Timeframe 1d is not usable" in reason for reason in result.block_reasons)


def test_safety_gate_distinguishes_incomplete_series_from_missing_timeframe() -> None:
    report = _report(BULLISH_5, zones_1h=BUY_ZONES)
    analyses = [
        item.model_copy(
            update={
                "series_complete": False,
                "limitations": ("Series incomplete: 2 missing intervals",),
            }
        )
        if item.interval == "4h"
        else item
        for item in report.timeframe_analyses
    ]
    report = report.model_copy(update={"timeframe_analyses": tuple(analyses)})
    result = _gate(report, evaluate_setup(report), proposal="BUY")
    assert result.decision == "WAIT"
    assert any("Incomplete candle series for timeframe 4h" in reason for reason in result.block_reasons)
