"""Deterministic tests for setup/scenario calculation and decision safety."""

from __future__ import annotations

from datetime import UTC, datetime
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
from app.strategy.decision_safety import DecisionSafetyGate
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


def _validated_price() -> ValidatedPrice:
    return ValidatedPrice(
        exchange="BINANCE",
        market="SPOT",
        symbol="BTCUSDT",
        price=PRICE,
        market_event_timestamp=NOW,
        received_timestamp=NOW,
        validated_timestamp=NOW,
        age_ms_at_validation=10,
        source="binance_spot_rest",
        event_id="t1",
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
    zones = (
        _zone("support", "95.00", "96.00"),
        _zone("resistance", "110.00", "111.00"),
        _zone("resistance", "120.00", "121.00"),
    )
    report = _report(
        {"5m": "bullish", "15m": "bullish", "1h": "bullish", "4h": "bullish", "1d": "bullish"},
        zones_1h=zones,
    )
    outcome = evaluate_setup(report)
    assert outcome.proposed_decision == "BUY"
    scenario = outcome.scenario
    assert scenario is not None
    # Entry band = price +/- 0.10*ATR(2.0) = 99.8 - 100.2
    assert scenario.entry_zone.lower == Decimal("99.80")
    assert scenario.entry_zone.upper == Decimal("100.20")
    # Stop = support lower 95.00 - 0.25*ATR(2.0)=0.5 -> 94.50
    assert scenario.stop_loss.price == Decimal("94.50")
    # TP1 = first resistance lower bound above entry = 110.00
    assert scenario.take_profit_1.price == Decimal("110.00")
    assert scenario.take_profit_2 is not None
    assert scenario.take_profit_2.price == Decimal("120.00")
    # risk = 100 - 94.5 = 5.5 ; reward = 110 - 100 = 10 ; R:R = 1.82
    assert scenario.risk_reward_ratio == Decimal("1.82")


def test_wait_when_risk_reward_too_low() -> None:
    zones = (
        _zone("support", "98.00", "99.00"),  # stop ~97.5 -> risk ~2.5
        _zone("resistance", "101.00", "102.00"),  # reward ~1 -> R:R < 1.5
    )
    report = _report(
        {"5m": "bullish", "15m": "bullish", "1h": "bullish", "4h": "bullish", "1d": "bullish"},
        zones_1h=zones,
    )
    outcome = evaluate_setup(report)
    assert outcome.proposed_decision == "WAIT"
    assert any("Risk/reward" in reason for reason in outcome.blocking_reasons)


def test_wait_when_no_target_zone() -> None:
    zones = (_zone("support", "95.00", "96.00"),)
    report = _report(
        {"5m": "bullish", "15m": "bullish", "1h": "bullish", "4h": "bullish", "1d": "bullish"},
        zones_1h=zones,
    )
    outcome = evaluate_setup(report)
    assert outcome.proposed_decision == "WAIT"


def test_sell_scenario_for_bearish_alignment() -> None:
    zones = (
        _zone("support", "90.00", "91.00"),
        _zone("resistance", "104.00", "105.00"),
    )
    report = _report(
        {"5m": "bearish", "15m": "bearish", "1h": "bearish", "4h": "bearish", "1d": "bearish"},
        zones_1h=zones,
    )
    outcome = evaluate_setup(report)
    assert outcome.proposed_decision == "SELL"
    scenario = outcome.scenario
    assert scenario is not None
    assert scenario.direction == "bearish"
    # Stop above resistance upper 105 + 0.5 = 105.50; TP1 = support upper 91.00
    assert scenario.stop_loss.price == Decimal("105.50")
    assert scenario.take_profit_1.price == Decimal("91.00")


def test_high_expanding_volatility_blocks_setup() -> None:
    zones = (
        _zone("support", "95.00", "96.00"),
        _zone("resistance", "110.00", "111.00"),
    )
    report = _report(
        {"5m": "bullish", "15m": "bullish", "1h": "bullish", "4h": "bullish", "1d": "bullish"},
        zones_1h=zones,
    )
    # Patch the 1h analysis volatility to high+expanding.
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


def test_safety_gate_passes_clean_buy() -> None:
    zones = (
        _zone("support", "95.00", "96.00"),
        _zone("resistance", "110.00", "111.00"),
    )
    report = _report(
        {"5m": "bullish", "15m": "bullish", "1h": "bullish", "4h": "bullish", "1d": "bullish"},
        zones_1h=zones,
    )
    outcome = evaluate_setup(report)
    result = DecisionSafetyGate().evaluate(report, outcome, _validated_price())
    assert result.decision == "BUY"
    assert result.scenario is not None
    assert not result.blocked


def test_safety_gate_blocks_on_stale_price() -> None:
    zones = (
        _zone("support", "95.00", "96.00"),
        _zone("resistance", "110.00", "111.00"),
    )
    report = _report(
        {"5m": "bullish", "15m": "bullish", "1h": "bullish", "4h": "bullish", "1d": "bullish"},
        zones_1h=zones,
    )
    outcome = evaluate_setup(report)
    stale = _validated_price().model_copy(update={"age_ms_at_validation": 5000})
    result = DecisionSafetyGate().evaluate(report, outcome, stale)
    assert result.decision == "WAIT"
    assert result.blocked
    assert any("3,000 ms" in r for r in result.block_reasons)


def test_safety_gate_blocks_on_incomplete_series() -> None:
    zones = (
        _zone("support", "95.00", "96.00"),
        _zone("resistance", "110.00", "111.00"),
    )
    report = _report(
        {"5m": "bullish", "15m": "bullish", "1h": "bullish", "4h": "bullish", "1d": "bullish"},
        zones_1h=zones,
    )
    analyses = [
        item.model_copy(update={"series_complete": False}) if item.interval == "4h" else item
        for item in report.timeframe_analyses
    ]
    report = report.model_copy(update={"timeframe_analyses": tuple(analyses)})
    outcome = evaluate_setup(report)
    result = DecisionSafetyGate().evaluate(report, outcome, _validated_price())
    assert result.decision == "WAIT"
    assert any("Incomplete" in r for r in result.block_reasons)


def test_safety_gate_blocks_on_missing_timeframe() -> None:
    report = _report({"1h": "bullish"}, alignment_status="insufficient")
    outcome = evaluate_setup(report)
    result = DecisionSafetyGate().evaluate(report, outcome, _validated_price())
    assert result.decision == "WAIT"
    assert any("Missing timeframe" in r for r in result.block_reasons)


def test_safety_gate_requires_provenance_when_configured() -> None:
    zones = (
        _zone("support", "95.00", "96.00"),
        _zone("resistance", "110.00", "111.00"),
    )
    report = _report(
        {"5m": "bullish", "15m": "bullish", "1h": "bullish", "4h": "bullish", "1d": "bullish"},
        zones_1h=zones,
    )
    # Strip snapshot ids.
    analyses = [item.model_copy(update={"snapshot_id": None}) for item in report.timeframe_analyses]
    report = report.model_copy(
        update={
            "timeframe_analyses": tuple(analyses),
            "current_price_snapshot_id": None,
        }
    )
    outcome = evaluate_setup(report)
    gate = DecisionSafetyGate(require_provenance=True)
    result = gate.evaluate(report, outcome, _validated_price())
    assert result.decision == "WAIT"
    assert any("provenance" in r.lower() for r in result.block_reasons)
