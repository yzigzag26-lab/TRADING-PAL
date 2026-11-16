"""Fail-closed validation for current market-price consumption."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.market_data.models import PriceEvent, ValidatedPrice


MAX_PRICE_AGE_MS = 3_000


class MarketDataUnavailable(Exception):
    """Raised when current market data cannot safely support an analysis."""


@dataclass(frozen=True, slots=True)
class FreshnessPolicy:
    """Centralized owner-approved freshness policy for price events."""

    max_price_age_ms: int = MAX_PRICE_AGE_MS

    def __post_init__(self) -> None:
        if self.max_price_age_ms != MAX_PRICE_AGE_MS:
            raise ValueError("Gate 3 price freshness is locked at 3,000 milliseconds")


def validate_price_event(
    event: PriceEvent,
    *,
    now: datetime | None = None,
    source_healthy: bool = True,
    clock_healthy: bool = True,
    policy: FreshnessPolicy = FreshnessPolicy(),
) -> ValidatedPrice:
    """Validate source provenance and event age immediately before consumption.

    The source market-event timestamp is authoritative. Receive time is retained
    for provenance and is never substituted for the exchange timestamp.
    """
    if not source_healthy:
        raise MarketDataUnavailable("Binance market-data source is not healthy")
    if not clock_healthy:
        raise MarketDataUnavailable("Baymax clock health is not verified")

    validation_time = now or datetime.now(timezone.utc)
    if validation_time.tzinfo is None or validation_time.utcoffset() is None:
        raise MarketDataUnavailable("Validation clock must be timezone-aware")
    validation_time = validation_time.astimezone(timezone.utc)

    age_ms = (validation_time - event.market_event_timestamp).total_seconds() * 1000
    if age_ms < 0:
        raise MarketDataUnavailable("Market event timestamp is in the future")
    age_ms_int = int(age_ms)
    if age_ms > policy.max_price_age_ms:
        raise MarketDataUnavailable("Latest verified price is older than 3 seconds")

    return ValidatedPrice(
        exchange=event.exchange,
        market=event.market,
        symbol=event.symbol,
        price=event.price,
        market_event_timestamp=event.market_event_timestamp,
        received_timestamp=event.received_timestamp,
        validated_timestamp=validation_time,
        age_ms_at_validation=age_ms_int,
        source=event.source,
        event_id=event.event_id,
    )
