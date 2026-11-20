"""Deterministic support/resistance zone derivation from swing points.

Zones are clusters of confirmed swing extremes. A cluster forms when swing
prices fall within ``cluster_tolerance`` of each other, expressed as the
larger of ``ATR_FRACTION * ATR`` and ``MIN_PRICE_FRACTION * price`` so zones
scale with volatility and instrument price.

- ``touches`` counts the distinct swing points inside the cluster.
- ``strength`` is ``min(1, touches / STRENGTH_SATURATION)`` — more reactions at
  a level mean stronger evidence, capped at 5 touches.
- A zone is ``active`` unless a closed candle after its most recent touch
  closed through it by more than ``INVALIDATION_ATR_FRACTION * ATR``.
- Zones are never presented as guaranteed reversal points; they are evidence
  areas derived only from validated candles.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from app.intelligence.schemas import PriceZone
from app.intelligence.structure import SwingPoint, detect_swings
from app.market_data.candles import HistoricalCandle

ATR_FRACTION = 0.5
MIN_PRICE_FRACTION = 0.001
STRENGTH_SATURATION = 5
INVALIDATION_ATR_FRACTION = 0.25
MAX_ZONES_PER_SIDE = 4
ZONE_LOOKBACK_CANDLES = 300


def _tolerance(price: Decimal, atr_value: float | None) -> Decimal:
    price_fraction = price * Decimal(str(MIN_PRICE_FRACTION))
    if atr_value is None or atr_value <= 0:
        return price_fraction
    atr_fraction = Decimal(str(atr_value)) * Decimal(str(ATR_FRACTION))
    return max(price_fraction, atr_fraction)


def _cluster(points: Sequence[SwingPoint], tolerance: Decimal) -> list[list[SwingPoint]]:
    """Group sorted swing prices into clusters separated by more than tolerance."""
    if not points:
        return []
    ordered = sorted(points, key=lambda point: point.price)
    clusters: list[list[SwingPoint]] = [[ordered[0]]]
    for point in ordered[1:]:
        cluster = clusters[-1]
        if point.price - cluster[-1].price <= tolerance:
            cluster.append(point)
        else:
            clusters.append([point])
    return clusters


def derive_zones(
    candles: Sequence[HistoricalCandle],
    *,
    timeframe: str,
    atr_value: float | None,
    swing_window: int = 3,
) -> tuple[PriceZone, ...]:
    """Derive active support and resistance zones from confirmed swings."""
    if len(candles) < 2 * swing_window + 3:
        return ()
    analyzed = candles[-ZONE_LOOKBACK_CANDLES:]
    swings = [
        swing
        for swing in detect_swings(analyzed, window=swing_window)
        if swing.kind in {"high", "low"}
    ]
    if not swings:
        return ()

    reference_price = analyzed[-1].close
    tolerance = _tolerance(reference_price, atr_value)
    zones: list[PriceZone] = []
    invalidation_buffer = (
        Decimal(str(atr_value)) * Decimal(str(INVALIDATION_ATR_FRACTION))
        if atr_value and atr_value > 0
        else tolerance
    )

    for side, kind in (("resistance", "high"), ("support", "low")):
        points = [swing for swing in swings if swing.kind == kind]
        clusters = _cluster(points, tolerance)
        candidates: list[PriceZone] = []
        for cluster in clusters:
            lower = min(point.price for point in cluster)
            upper = max(point.price for point in cluster)
            touches = len(cluster)
            strength = min(1.0, touches / STRENGTH_SATURATION)
            latest_touch_index = max(point.index for point in cluster)
            # Invalidation: any closed candle after the latest touch that
            # closed through the zone by more than the ATR buffer.
            active = True
            reason: str | None = None
            for candle in analyzed[latest_touch_index + 1 :]:
                if side == "resistance" and candle.close > upper + invalidation_buffer:
                    active = False
                    reason = f"Closed above zone at {candle.close}"
                    break
                if side == "support" and candle.close < lower - invalidation_buffer:
                    active = False
                    reason = f"Closed below zone at {candle.close}"
                    break
            candidates.append(
                PriceZone(
                    side=side,  # type: ignore[arg-type]
                    lower=lower,
                    upper=upper,
                    timeframe=timeframe,
                    method="swing_cluster_v1",
                    touches=touches,
                    strength=round(strength, 4),
                    active=active,
                    source_open_times=tuple(sorted(point.open_time for point in cluster)),
                    invalidated_reason=reason,
                )
            )
        # Rank by strength then recency; keep the best MAX_ZONES_PER_SIDE.
        candidates.sort(
            key=lambda zone: (
                zone.strength,
                max(zone.source_open_times)
                if zone.source_open_times
                else datetime.min.replace(tzinfo=UTC),
            ),
            reverse=True,
        )
        zones.extend(candidates[:MAX_ZONES_PER_SIDE])

    # A zone exactly at the current price is the most relevant; ordering is
    # preserved per side by strength/recency for downstream consumers.
    return tuple(zones)


__all__ = [
    "ATR_FRACTION",
    "INVALIDATION_ATR_FRACTION",
    "MAX_ZONES_PER_SIDE",
    "MIN_PRICE_FRACTION",
    "STRENGTH_SATURATION",
    "ZONE_LOOKBACK_CANDLES",
    "derive_zones",
]
