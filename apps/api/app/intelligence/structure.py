"""Deterministic swing-point and market-structure detection.

Methodology (Gate 4 v1):

- A swing high at index ``i`` requires ``high[i]`` to be strictly greater than
  every high in the ``swing_window`` candles on each side. A swing low is the
  mirror using lows. ``swing_window`` defaults to 3.
- A swing point is only confirmed once ``swing_window`` subsequent candles have
  closed, so detection never uses future data: pivots are searched only within
  ``candles[: len(candles) - swing_window]``.
- Consecutive confirmed swing highs/lows are classified as higher-high,
  lower-high, higher-low or lower-low relative to the previous same-type swing.
- Break of structure (BOS): a closed candle closes beyond the most recent
  confirmed swing extreme in the direction of the prevailing swing sequence.
- Change of character (CHoCH): the first close beyond the opposite swing
  extreme while the prevailing sequence was opposite — a potential reversal.
- Consolidation: the last ``consolidation_lookback`` closed candles stay inside
  a band narrower than ``consolidation_atr_multiple`` times ATR.
- Breakout / failed breakout: a closed close beyond the prior
  ``breakout_lookback`` candle extreme; a failed breakout is a later closed
  candle closing back inside the range within ``failure_window`` candles.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.intelligence.schemas import StructureFinding, StructureKind
from app.market_data.candles import HistoricalCandle

SWING_WINDOW = 3
CONSOLIDATION_LOOKBACK = 20
CONSOLIDATION_ATR_MULTIPLE = 2.0
BREAKOUT_LOOKBACK = 20
FAILURE_WINDOW = 5


@dataclass(frozen=True, slots=True)
class SwingPoint:
    """A confirmed pivot with the candles that confirmed it."""

    index: int
    kind: str  # "high" or "low"
    price: Decimal
    open_time: datetime
    confirmed_at_index: int


def detect_swings(
    candles: Sequence[HistoricalCandle],
    *,
    window: int = SWING_WINDOW,
) -> tuple[SwingPoint, ...]:
    """Return confirmed swing highs and lows in chronological order."""
    swings: list[SwingPoint] = []
    last_pivotable = len(candles) - window - 1
    for index in range(window, last_pivotable + 1):
        high = candles[index].high
        low = candles[index].low
        left_highs = [candles[j].high for j in range(index - window, index)]
        right_highs = [candles[j].high for j in range(index + 1, index + window + 1)]
        left_lows = [candles[j].low for j in range(index - window, index)]
        right_lows = [candles[j].low for j in range(index + 1, index + window + 1)]
        confirmed_at = index + window
        if all(high > value for value in left_highs + right_highs):
            swings.append(SwingPoint(index, "high", high, candles[index].open_time, confirmed_at))
        if all(low < value for value in left_lows + right_lows):
            swings.append(SwingPoint(index, "low", low, candles[index].open_time, confirmed_at))
    swings.sort(key=lambda point: point.index)
    return tuple(swings)


def _sequence_findings(
    swings: Sequence[SwingPoint],
) -> list[tuple[StructureKind, SwingPoint, SwingPoint]]:
    """Classify HH/HL/LH/LL between consecutive same-type swings."""
    findings: list[tuple[StructureKind, SwingPoint, SwingPoint]] = []
    last_high: SwingPoint | None = None
    last_low: SwingPoint | None = None
    for swing in swings:
        if swing.kind == "high":
            if last_high is not None:
                if swing.price > last_high.price:
                    findings.append(("higher_high", last_high, swing))
                elif swing.price < last_high.price:
                    findings.append(("lower_high", last_high, swing))
            last_high = swing
        else:
            if last_low is not None:
                if swing.price > last_low.price:
                    findings.append(("higher_low", last_low, swing))
                elif swing.price < last_low.price:
                    findings.append(("lower_low", last_low, swing))
            last_low = swing
    return findings


def analyze_structure(
    candles: Sequence[HistoricalCandle],
    *,
    atr_value: float | None = None,
    swing_window: int = SWING_WINDOW,
) -> tuple[StructureFinding, ...]:
    """Detect structure findings on a closed-candle series."""
    findings: list[StructureFinding] = []
    swings = detect_swings(candles, window=swing_window)
    if len(swings) < 4:
        return (
            StructureFinding(
                kind="consolidation",
                detail="Insufficient confirmed swing points for structure analysis",
                confirmed=False,
            ),
        )

    for kind, previous, current in _sequence_findings(swings)[-6:]:
        findings.append(
            StructureFinding(
                kind=kind,
                detail=(
                    f"{kind.replace('_', ' ')}: swing {previous.kind} moved from "
                    f"{previous.price} to {current.price}"
                ),
                reference_open_times=(previous.open_time, current.open_time),
                confirmed=True,
            )
        )

    swing_highs = [s for s in swings if s.kind == "high"]
    swing_lows = [s for s in swings if s.kind == "low"]
    last_high = swing_highs[-1] if swing_highs else None
    last_low = swing_lows[-1] if swing_lows else None
    last_close = candles[-1].close

    # Determine prevailing direction from the latest HH/HL vs LH/LL sequence.
    sequence = _sequence_findings(swings)
    bullish_sequence = sum(
        1 for kind, _, _ in sequence[-4:] if kind in {"higher_high", "higher_low"}
    )
    bearish_sequence = sum(1 for kind, _, _ in sequence[-4:] if kind in {"lower_high", "lower_low"})
    prevailing_up = bullish_sequence > bearish_sequence

    if last_high is not None and last_close > last_high.price:
        findings.append(
            StructureFinding(
                kind="break_of_structure" if prevailing_up else "change_of_character",
                detail=(
                    f"Latest closed candle closed at {last_close} beyond swing high "
                    f"{last_high.price}"
                ),
                reference_open_times=(last_high.open_time, candles[-1].open_time),
                confirmed=True,
            )
        )
    elif last_low is not None and last_close < last_low.price:
        findings.append(
            StructureFinding(
                kind="break_of_structure" if not prevailing_up else "change_of_character",
                detail=(
                    f"Latest closed candle closed at {last_close} below swing low {last_low.price}"
                ),
                reference_open_times=(last_low.open_time, candles[-1].open_time),
                confirmed=True,
            )
        )

    # Consolidation: recent candles inside a narrow ATR-defined band.
    lookback = min(CONSOLIDATION_LOOKBACK, len(candles))
    recent = candles[-lookback:]
    band = max(candle.high for candle in recent) - min(candle.low for candle in recent)
    close_price = float(last_close)
    if atr_value and atr_value > 0 and close_price > 0:
        band_ratio = float(band) / close_price
        atr_ratio = atr_value / close_price
        if band_ratio < CONSOLIDATION_ATR_MULTIPLE * atr_ratio and not any(
            f.kind in {"break_of_structure", "change_of_character"} for f in findings
        ):
            findings.append(
                StructureFinding(
                    kind="consolidation",
                    detail=(
                        f"Last {lookback} candles range within "
                        f"{band_ratio * 100:.2f}% of price (ATR ratio "
                        f"{atr_ratio * 100:.2f}%)"
                    ),
                    reference_open_times=(recent[0].open_time, recent[-1].open_time),
                    confirmed=True,
                )
            )

    # Breakout / failed breakout against the prior lookback window.
    window_start = max(0, len(candles) - BREAKOUT_LOOKBACK - 1)
    prior = candles[window_start : len(candles) - 1]
    if prior:
        prior_high = max(candle.high for candle in prior)
        prior_low = min(candle.low for candle in prior)
        last = candles[-1]
        if last.close > prior_high:
            findings.append(
                StructureFinding(
                    kind="breakout",
                    detail=(
                        f"Closed at {last.close} above prior "
                        f"{BREAKOUT_LOOKBACK}-candle high {prior_high}"
                    ),
                    reference_open_times=(prior[-1].open_time, last.open_time),
                    confirmed=True,
                )
            )
            # Failed breakout: a later close back inside the range.
            for candle in candles[-FAILURE_WINDOW:]:
                if candle is last:
                    continue
                if candle.close < prior_high:
                    findings.append(
                        StructureFinding(
                            kind="failed_breakout",
                            detail=(
                                f"Price closed back below breakout level {prior_high} "
                                f"at {candle.close}"
                            ),
                            reference_open_times=(last.open_time, candle.open_time),
                            confirmed=True,
                        )
                    )
                    break
        elif last.close < prior_low:
            findings.append(
                StructureFinding(
                    kind="breakout",
                    detail=(
                        f"Closed at {last.close} below prior "
                        f"{BREAKOUT_LOOKBACK}-candle low {prior_low}"
                    ),
                    reference_open_times=(prior[-1].open_time, last.open_time),
                    confirmed=True,
                )
            )
            for candle in candles[-FAILURE_WINDOW:]:
                if candle is last:
                    continue
                if candle.close > prior_low:
                    findings.append(
                        StructureFinding(
                            kind="failed_breakout",
                            detail=(
                                f"Price closed back above breakdown level {prior_low} "
                                f"at {candle.close}"
                            ),
                            reference_open_times=(last.open_time, candle.open_time),
                            confirmed=True,
                        )
                    )
                    break

    return tuple(findings)


__all__ = [
    "BREAKOUT_LOOKBACK",
    "CONSOLIDATION_ATR_MULTIPLE",
    "CONSOLIDATION_LOOKBACK",
    "FAILURE_WINDOW",
    "SWING_WINDOW",
    "SwingPoint",
    "analyze_structure",
    "detect_swings",
]
