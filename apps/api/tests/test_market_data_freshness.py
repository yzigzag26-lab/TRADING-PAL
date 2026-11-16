"""Deterministic tests for the Gate 3 three-second freshness boundary."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.market_data.freshness import (
    MAX_PRICE_AGE_MS,
    FreshnessPolicy,
    MarketDataUnavailable,
    validate_price_event,
)
from app.market_data.models import PriceEvent

NOW = datetime(2026, 11, 16, 12, 0, 0, tzinfo=timezone.utc)


def make_event(*, age_ms: int = 1_000, event_time: datetime | None = None) -> PriceEvent:
    timestamp = event_time or NOW - timedelta(milliseconds=age_ms)
    return PriceEvent(
        symbol="btcusdt",
        price="95000.12345678",
        market_event_timestamp=timestamp,
        exchange_event_timestamp=timestamp,
        received_timestamp=NOW,
        source="binance_spot_websocket",
        event_id="trade-1",
    )


def test_owner_approved_threshold_is_exactly_three_seconds() -> None:
    assert MAX_PRICE_AGE_MS == 3_000
    assert FreshnessPolicy().max_price_age_ms == 3_000
    with pytest.raises(ValueError):
        FreshnessPolicy(max_price_age_ms=3_001)


@pytest.mark.parametrize("age_ms", [0, 1, 2_999, 3_000])
def test_price_at_or_inside_boundary_is_accepted(age_ms: int) -> None:
    result = validate_price_event(make_event(age_ms=age_ms), now=NOW)
    assert result.age_ms_at_validation == age_ms
    assert result.price == Decimal("95000.12345678")
    assert result.symbol == "BTCUSDT"


@pytest.mark.parametrize("age_ms", [3_001, 4_000, 60_000])
def test_price_older_than_boundary_is_rejected(age_ms: int) -> None:
    with pytest.raises(MarketDataUnavailable, match="older than 3 seconds"):
        validate_price_event(make_event(age_ms=age_ms), now=NOW)


def test_future_source_timestamp_is_rejected() -> None:
    with pytest.raises(MarketDataUnavailable, match="in the future"):
        validate_price_event(make_event(event_time=NOW + timedelta(milliseconds=1)), now=NOW)


def test_unhealthy_source_fails_closed() -> None:
    with pytest.raises(MarketDataUnavailable, match="source is not healthy"):
        validate_price_event(make_event(), now=NOW, source_healthy=False)


def test_unhealthy_clock_fails_closed() -> None:
    with pytest.raises(MarketDataUnavailable, match="clock health"):
        validate_price_event(make_event(), now=NOW, clock_healthy=False)


def test_naive_timestamps_are_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        make_event(event_time=datetime(2026, 11, 16, 12, 0, 0))


@pytest.mark.parametrize("price", ["0", "-1", "NaN", "Infinity", "not-a-price"])
def test_invalid_prices_are_rejected(price: str) -> None:
    with pytest.raises(ValidationError):
        PriceEvent(
            symbol="BTCUSDT",
            price=price,
            market_event_timestamp=NOW,
            received_timestamp=NOW,
            source="binance_spot_rest",
        )
