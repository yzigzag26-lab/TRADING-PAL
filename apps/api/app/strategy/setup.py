"""Deterministic setup and scenario calculation (Gate 4).

Methodology v1 — every level is derived from validated evidence, never
invented:

- Bias comes only from multi-timeframe alignment; ``aligned_bullish`` may
  produce BUY, ``aligned_bearish`` may produce SELL (an exit/reduction
  assessment — Binance Spot V1 has no short exposure), anything else is WAIT.
- Volatility gate: ``high`` + ``expanding`` volatility on the setup timeframe
  blocks scenario construction (WAIT).
- Setup timeframe: ``1h`` when usable, otherwise the first usable timeframe in
  ``SETUP_TIMEFRAME_PREFERENCE`` order.
- Entry zone: the active support (BUY) or resistance (SELL) zone containing or
  nearest the current price; otherwise a narrow band of ``ENTRY_ATR_FRACTION *
  ATR`` around the validated price.
- Stop-loss: beyond the far side of the protective zone minus
  ``STOP_ATR_BUFFER * ATR``.
- Take-profit 1: the near boundary of the nearest opposing active zone.
  Take-profit 2: the next opposing zone when present.
- The setup is rejected (WAIT) unless ``MIN_RISK_REWARD`` is met between the
  entry midpoint and TP1, and unless both a protective zone and a target zone
  exist. Levels are never manufactured to force a recommendation.
"""

from __future__ import annotations

from decimal import Decimal

from app.intelligence.schemas import MarketIntelligenceReport, PriceZone, TimeframeAnalysis
from app.strategy.schemas import (
    BiasDirection,
    Decision,
    EntryZone,
    PriceLevel,
    Scenario,
    StrategyOutcome,
)

SETUP_TIMEFRAME_PREFERENCE: tuple[str, ...] = ("1h", "15m", "4h", "5m", "1d")
MIN_RISK_REWARD = Decimal("1.5")
STOP_ATR_BUFFER = 0.25
ENTRY_ATR_FRACTION = 0.10
MIN_SETUP_CANDLES = 60


def _decimal(value: float | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _atr_of(analysis: TimeframeAnalysis) -> Decimal | None:
    for reading in analysis.indicators:
        if reading.name == "ATR" and reading.sufficient_history:
            return _decimal(reading.values.get("value"))
    return None


def _select_setup_timeframe(report: MarketIntelligenceReport) -> TimeframeAnalysis | None:
    by_interval = {item.interval: item for item in report.timeframe_analyses}
    for interval in SETUP_TIMEFRAME_PREFERENCE:
        item = by_interval.get(interval)
        if item is not None and item.usable:
            return item
    return None


def _zones(analysis: TimeframeAnalysis, side: str) -> list[PriceZone]:
    return sorted(
        (zone for zone in analysis.zones if zone.side == side and zone.active),
        key=lambda zone: zone.lower,
    )


def _containing_zone(zones: list[PriceZone], price: Decimal) -> PriceZone | None:
    for zone in zones:
        if zone.lower <= price <= zone.upper:
            return zone
    return None


def _protective_zone(zones: list[PriceZone], price: Decimal, *, bullish: bool) -> PriceZone | None:
    """Nearest protective zone: containing first, then closest beyond price."""
    containing = _containing_zone(zones, price)
    if containing is not None:
        return containing
    if bullish:
        below = [zone for zone in zones if zone.upper <= price]
        return max(below, key=lambda zone: zone.upper) if below else (zones[0] if zones else None)
    above = [zone for zone in zones if zone.lower >= price]
    return min(above, key=lambda zone: zone.lower) if above else (zones[-1] if zones else None)


def evaluate_setup(report: MarketIntelligenceReport) -> StrategyOutcome:
    """Evaluate the intelligence report and build a scenario when justified."""
    reasons: list[str] = []
    blocking: list[str] = []

    if report.data_quality == "insufficient" or report.readiness == "blocked":
        return StrategyOutcome(
            proposed_decision="WAIT",
            direction="neutral",
            reasons=("Insufficient verified market data for a recommendation",),
            blocking_reasons=tuple(report.limitations[:5]) or ("data_quality=insufficient",),
        )

    status = report.alignment.status
    if status == "aligned_bullish":
        direction: BiasDirection = "bullish"
    elif status == "aligned_bearish":
        direction = "bearish"
    else:
        direction = "neutral"
        blocking.append(f"Timeframe alignment is {status}; no directional bias")

    setup_tf = _select_setup_timeframe(report)
    if setup_tf is None:
        blocking.append("No usable timeframe for scenario construction")
        return StrategyOutcome(
            proposed_decision="WAIT",
            direction=direction,
            reasons=tuple(reasons),
            blocking_reasons=tuple(blocking),
        )
    reasons.append(f"Setup timeframe: {setup_tf.interval}")

    atr = _atr_of(setup_tf)
    price = Decimal(report.current_price)
    if atr is None or atr <= 0:
        blocking.append("ATR unavailable; volatility-scaled levels cannot be derived")

    volatility = setup_tf.volatility
    if volatility.level == "high" and volatility.direction == "expanding":
        blocking.append("Volatility is high and expanding; setup risk is unsuitable")
        return StrategyOutcome(
            proposed_decision="WAIT",
            direction=direction,
            reasons=tuple(reasons),
            blocking_reasons=tuple(blocking),
        )

    if direction == "neutral" or atr is None or atr <= 0:
        return StrategyOutcome(
            proposed_decision="WAIT",
            direction=direction,
            reasons=tuple(reasons),
            blocking_reasons=tuple(blocking),
        )

    supports = _zones(setup_tf, "support")
    resistances = _zones(setup_tf, "resistance")
    protective_zones = supports if direction == "bullish" else resistances
    target_zones = resistances if direction == "bullish" else supports

    protective = _protective_zone(protective_zones, price, bullish=direction == "bullish")
    if protective is None:
        blocking.append(
            f"No active {'support' if direction == 'bullish' else 'resistance'} "
            "zone for stop-loss derivation"
        )

    # Entry zone.
    containing = _containing_zone(protective_zones, price)
    band = atr * Decimal(str(ENTRY_ATR_FRACTION))
    if containing is not None:
        entry_zone = EntryZone(
            lower=containing.lower,
            upper=containing.upper,
            method=f"zone_containing_price_{setup_tf.interval}",
        )
    else:
        entry_zone = EntryZone(
            lower=price - band,
            upper=price + band,
            method=f"atr_band_{setup_tf.interval}",
        )
    entry_mid = (entry_zone.lower + entry_zone.upper) / 2

    # Stop-loss beyond the protective zone.
    if protective is not None:
        if direction == "bullish":
            stop_price = protective.lower - atr * Decimal(str(STOP_ATR_BUFFER))
            sl_method = f"below_{setup_tf.interval}_support_zone_minus_atr_buffer"
        else:
            stop_price = protective.upper + atr * Decimal(str(STOP_ATR_BUFFER))
            sl_method = f"above_{setup_tf.interval}_resistance_zone_plus_atr_buffer"
    else:
        stop_price = Decimal(0)
        sl_method = "unavailable"

    # Targets from opposing zones.
    if direction == "bullish":
        tp1_zone = next((zone for zone in target_zones if zone.lower > entry_zone.upper), None)
        tp2_zone = (
            next((zone for zone in target_zones if zone.lower > tp1_zone.upper), None)
            if tp1_zone is not None
            else None
        )
    else:
        tp1_zone = next(
            (zone for zone in reversed(target_zones) if zone.upper < entry_zone.lower),
            None,
        )
        tp2_zone = (
            next(
                (
                    zone
                    for zone in reversed(target_zones)
                    if tp1_zone is not None and zone.upper < tp1_zone.lower
                ),
                None,
            )
            if tp1_zone is not None
            else None
        )
    if tp1_zone is None:
        blocking.append("No opposing zone available for a take-profit target")

    if protective is None or tp1_zone is None:
        return StrategyOutcome(
            proposed_decision="WAIT",
            direction=direction,
            reasons=tuple(reasons),
            blocking_reasons=tuple(blocking),
        )

    if direction == "bullish":
        risk = entry_mid - stop_price
        reward = tp1_zone.lower - entry_mid
        tp1_price = tp1_zone.lower
        tp1_method = f"{setup_tf.interval}_resistance_zone_lower"
        tp2_price = tp2_zone.lower if tp2_zone is not None else None
        tp2_method = f"{setup_tf.interval}_next_resistance_zone_lower" if tp2_zone else None
        invalidation = (
            f"Invalidated by a closed {setup_tf.interval} candle below "
            f"{stop_price} (below the protective support zone)."
        )
    else:
        risk = stop_price - entry_mid
        reward = entry_mid - tp1_zone.upper
        tp1_price = tp1_zone.upper
        tp1_method = f"{setup_tf.interval}_support_zone_upper"
        tp2_price = tp2_zone.upper if tp2_zone is not None else None
        tp2_method = f"{setup_tf.interval}_next_support_zone_upper" if tp2_zone else None
        invalidation = (
            f"Invalidated by a closed {setup_tf.interval} candle above "
            f"{stop_price} (above the protective resistance zone)."
        )

    if risk <= 0 or reward <= 0:
        blocking.append("Computed risk or reward distance is not positive")
        return StrategyOutcome(
            proposed_decision="WAIT",
            direction=direction,
            reasons=tuple(reasons),
            blocking_reasons=tuple(blocking),
        )
    ratio = reward / risk
    reasons.append(
        f"Entry zone {entry_zone.lower}-{entry_zone.upper}, stop {stop_price}, "
        f"TP1 {tp1_price}, R:R {ratio:.2f}"
    )
    if ratio < MIN_RISK_REWARD:
        blocking.append(f"Risk/reward {ratio:.2f} below minimum {MIN_RISK_REWARD}")
        return StrategyOutcome(
            proposed_decision="WAIT",
            direction=direction,
            reasons=tuple(reasons),
            blocking_reasons=tuple(blocking),
        )

    proposed: Decision = "BUY" if direction == "bullish" else "SELL"
    scenario = Scenario(
        decision=proposed,
        direction=direction,
        entry_zone=entry_zone,
        stop_loss=PriceLevel(price=stop_price, method=sl_method),
        take_profit_1=PriceLevel(price=tp1_price, method=tp1_method),
        take_profit_2=(
            PriceLevel(price=tp2_price, method=tp2_method)
            if tp2_price is not None and tp2_method is not None
            else None
        ),
        risk_distance=risk,
        reward_distance=reward,
        risk_reward_ratio=ratio.quantize(Decimal("0.01")),
        invalidation=invalidation,
        methodology="setup_zone_atr_v1",
    )
    return StrategyOutcome(
        proposed_decision=proposed,
        direction=direction,
        scenario=scenario,
        reasons=tuple(reasons),
        blocking_reasons=tuple(blocking),
    )


__all__ = [
    "ENTRY_ATR_FRACTION",
    "MIN_RISK_REWARD",
    "SETUP_TIMEFRAME_PREFERENCE",
    "STOP_ATR_BUFFER",
    "evaluate_setup",
]
