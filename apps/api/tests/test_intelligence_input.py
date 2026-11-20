"""Deterministic tests for the Gate 4 verified multi-timeframe input builder."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, TypeVar
from uuid import UUID, uuid4

import pytest

from app.intelligence.analyzer import ANALYSIS_TIMEFRAMES
from app.market_data.analysis_input import (
    CANDLES_PER_TIMEFRAME,
    MarketIntelligenceInputBuilder,
    MarketIntelligenceInputUnavailable,
    closed_window,
)
from app.market_data.candles import (
    BinanceInterval,
    HistoricalCandleSeries,
    is_interval_boundary,
)
from app.market_data.freshness import MarketDataUnavailable
from app.market_data.models import ValidatedPrice
from app.orchestration.requests import PreparedAnalysisInput
from tests.candle_helpers import candle_series, make_series

NOW = datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC)
SYMBOL = "BTCUSDT"


def _price() -> ValidatedPrice:
    return ValidatedPrice(
        exchange="BINANCE",
        market="SPOT",
        symbol=SYMBOL,
        price=Decimal("100"),
        market_event_timestamp=NOW,
        received_timestamp=NOW,
        validated_timestamp=NOW,
        age_ms_at_validation=10,
        source="binance_spot_rest",
        event_id="evt-1",
    )


def _prepared(**overrides: object) -> PreparedAnalysisInput:
    values: dict[str, object] = {
        "intent": "current_market",
        "market_data_required": True,
        "market_data_status": "ready",
        "current_price": _price(),
        "market_snapshot_id": uuid4(),
    }
    values.update(overrides)
    return PreparedAnalysisInput(**values)  # type: ignore[arg-type]


class _FakeHistorical:
    """Stand-in for BinanceHistoricalCandleService.fetch."""

    def __init__(self, *, fail_intervals: set[str] | None = None) -> None:
        self.fail_intervals = fail_intervals or set()
        self.calls: list[tuple[str, str]] = []

    async def fetch(
        self,
        symbol: str,
        interval: BinanceInterval,
        *,
        start_time: datetime,
        end_time: datetime,
        now: datetime | None = None,
    ) -> HistoricalCandleSeries:
        self.calls.append((symbol, interval))
        if interval in self.fail_intervals:
            raise MarketDataUnavailable("synthetic outage")
        # Generate candles inside the requested window so counts are realistic.
        step_seconds = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}[interval]
        count = int((end_time - start_time).total_seconds() // step_seconds) + 1
        candles = candle_series(count, interval, start=start_time)
        return make_series(candles, interval=interval, symbol=symbol)


class _FakeProvenance:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.historical_calls: list[object] = []
        self.price_calls: list[object] = []

    def record_historical_series(self, series, *, request_id=None) -> UUID:  # type: ignore[no-untyped-def]
        if self.fail:
            raise RuntimeError("db down")
        self.historical_calls.append(series)
        return uuid4()

    def record_price(self, price, *, request_id=None) -> UUID:  # type: ignore[no-untyped-def]
        self.price_calls.append(price)
        return uuid4()


T = TypeVar("T")


def _run(coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def test_build_fetches_all_five_timeframes() -> None:
    historical = _FakeHistorical()
    provenance = _FakeProvenance()
    builder = MarketIntelligenceInputBuilder(
        historical=historical,  # type: ignore[arg-type]
        provenance_repository=provenance,  # type: ignore[arg-type]
        require_provenance=False,
    )
    bundle = _run(builder.build(_prepared(), request_id=uuid4(), now=NOW))
    assert bundle.price.symbol == SYMBOL
    assert bundle.price_snapshot_id is not None
    assert set(bundle.timeframes) == set(ANALYSIS_TIMEFRAMES)
    assert len(historical.calls) == len(ANALYSIS_TIMEFRAMES)
    assert len(provenance.historical_calls) == len(ANALYSIS_TIMEFRAMES)
    for interval, entry in bundle.timeframes.items():
        assert entry.interval == interval
        assert entry.snapshot_id is not None
        assert entry.series.snapshot_id == entry.snapshot_id


def test_build_degrades_when_one_timeframe_fails() -> None:
    historical = _FakeHistorical(fail_intervals={"4h"})
    builder = MarketIntelligenceInputBuilder(
        historical=historical,  # type: ignore[arg-type]
        provenance_repository=_FakeProvenance(),  # type: ignore[arg-type]
        require_provenance=False,
    )
    bundle = _run(builder.build(_prepared(), now=NOW))
    assert "4h" not in bundle.timeframes
    assert set(bundle.timeframes) == {"5m", "15m", "1h", "1d"}


def test_build_requires_price_and_snapshot() -> None:
    builder = MarketIntelligenceInputBuilder(
        historical=_FakeHistorical(),  # type: ignore[arg-type]
        provenance_repository=None,
        require_provenance=False,
    )
    with pytest.raises(MarketIntelligenceInputUnavailable):
        _run(builder.build(_prepared(current_price=None, market_snapshot_id=None), now=NOW))


def test_build_blocks_when_provenance_required_but_missing() -> None:
    builder = MarketIntelligenceInputBuilder(
        historical=_FakeHistorical(),  # type: ignore[arg-type]
        provenance_repository=None,
        require_provenance=True,
    )
    with pytest.raises(MarketIntelligenceInputUnavailable):
        _run(builder.build(_prepared(), now=NOW))


def test_build_blocks_when_provenance_write_fails() -> None:
    builder = MarketIntelligenceInputBuilder(
        historical=_FakeHistorical(),  # type: ignore[arg-type]
        provenance_repository=_FakeProvenance(fail=True),  # type: ignore[arg-type]
        require_provenance=False,
    )
    with pytest.raises(MarketIntelligenceInputUnavailable):
        _run(builder.build(_prepared(), now=NOW))


def test_closed_window_ends_before_forming_candle() -> None:
    start, end = closed_window("1h", count=300, now=NOW)
    assert is_interval_boundary(start, "1h")
    assert is_interval_boundary(end, "1h")
    # ``end`` is the open boundary of the last fully closed candle; the candle
    # that opened at NOW's hour boundary is still forming and excluded.
    hour_boundary = NOW.replace(minute=0, second=0, microsecond=0)
    assert end == hour_boundary - timedelta(hours=1)
    assert end - start == timedelta(hours=299)


def test_closed_window_respects_interval_alignment() -> None:
    now = datetime(2026, 2, 1, 12, 34, 56, tzinfo=UTC)
    start, end = closed_window("15m", count=CANDLES_PER_TIMEFRAME, now=now)
    assert is_interval_boundary(start, "15m")
    assert is_interval_boundary(end, "15m")
    assert end < now


def test_builder_rejects_unsupported_timeframe() -> None:
    with pytest.raises(ValueError):
        MarketIntelligenceInputBuilder(
            historical=_FakeHistorical(),  # type: ignore[arg-type]
            provenance_repository=None,
            require_provenance=False,
            timeframes=("3w",),
        )
