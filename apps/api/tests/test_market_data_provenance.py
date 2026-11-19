"""Tests for persistent market-data provenance payload construction."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy.orm import Session, sessionmaker

from app.db.models.audit_log import AuditLog
from app.db.models.market_data_snapshot import MarketDataSnapshot
from app.market_data.candles import (
    HistoricalCandle,
    HistoricalCandleSeries,
    interval_close_time,
)
from app.market_data.freshness import validate_price_event
from app.market_data.models import PriceEvent
from app.market_data.provenance import MarketDataProvenanceRepository

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)


class FakeSession:
    def __init__(self) -> None:
        self.rows: list[MarketDataSnapshot | AuditLog] = []
        self.snapshot: MarketDataSnapshot | None = None

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def add(self, row: object) -> None:
        assert isinstance(row, (MarketDataSnapshot, AuditLog))
        self.rows.append(row)
        if isinstance(row, MarketDataSnapshot):
            self.snapshot = row

    def flush(self) -> None:
        if self.snapshot is not None and self.snapshot.id is None:
            self.snapshot.id = uuid4()

    def commit(self) -> None:
        return None

    def refresh(self, row: object) -> None:
        assert row is self.snapshot


class FakeSessionFactory:
    def __init__(self) -> None:
        self.session = FakeSession()

    def __call__(self) -> FakeSession:
        return self.session


def test_price_provenance_persists_source_timestamps_and_exact_decimal() -> None:
    factory = FakeSessionFactory()
    repository = MarketDataProvenanceRepository(cast(sessionmaker[Session], factory))
    event = PriceEvent(
        symbol="BTCUSDT",
        price=Decimal("95000.12345678"),
        market_event_timestamp=NOW - timedelta(milliseconds=300),
        exchange_event_timestamp=NOW - timedelta(milliseconds=250),
        received_timestamp=NOW - timedelta(milliseconds=100),
        source="binance_spot_websocket",
        event_id="12345",
    )
    price = validate_price_event(
        event,
        now=NOW,
        source_healthy=True,
        clock_healthy=True,
    )
    request_id = uuid4()

    snapshot_id = repository.record_price(price, request_id=request_id)
    row = factory.session.snapshot
    audit = next(item for item in factory.session.rows if isinstance(item, AuditLog))

    assert isinstance(snapshot_id, UUID)
    assert row is not None
    assert row.data_type == "trade_price"
    assert row.market_event_timestamp == event.market_event_timestamp
    assert row.exchange_event_timestamp == event.exchange_event_timestamp
    assert row.age_ms_at_validation == 300
    assert row.request_id == request_id
    assert row.payload == {"price": "95000.12345678", "event_id": "12345"}
    assert row.connection_state == "WEBSOCKET_HEALTHY"
    assert audit.event_type == "market_data.snapshot_recorded"
    assert audit.actor_type == "service"
    assert audit.resource_type == "market_data_snapshot"
    assert audit.resource_id == str(snapshot_id)
    assert audit.request_id == request_id
    assert audit.metadata_["source"] == "binance_spot_websocket"
    assert audit.metadata_["validation_state"] == "VALIDATED"
    assert "price" not in audit.metadata_


def test_historical_provenance_persists_incomplete_series_without_filling_gaps() -> None:
    factory = FakeSessionFactory()
    repository = MarketDataProvenanceRepository(cast(sessionmaker[Session], factory))
    start = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
    candle = HistoricalCandle(
        symbol="BTCUSDT",
        interval="1m",
        open_time=start,
        close_time=interval_close_time(start, "1m"),
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal("95"),
        close=Decimal("101"),
        base_volume=Decimal("2"),
        quote_volume=Decimal("200"),
        trade_count=4,
        taker_buy_base_volume=Decimal("1"),
        taker_buy_quote_volume=Decimal("100"),
        received_time=NOW,
        is_closed=True,
    )
    missing = start + timedelta(minutes=1)
    series = HistoricalCandleSeries(
        symbol="BTCUSDT",
        interval="1m",
        requested_start=start,
        requested_end=missing,
        candles=(candle,),
        missing_open_times=(missing,),
        complete=False,
        recovery_attempts=2,
    )

    snapshot_id = repository.record_historical_series(series)
    row = factory.session.snapshot
    audit = next(item for item in factory.session.rows if isinstance(item, AuditLog))

    assert isinstance(snapshot_id, UUID)
    assert row is not None
    assert row.data_type == "historical_ohlcv"
    assert row.is_complete is False
    assert row.validation_state == "INCOMPLETE"
    assert row.payload["missing_open_times"] == [missing.isoformat().replace("+00:00", "Z")]
    assert len(row.payload["candles"]) == 1
    assert audit.resource_id == str(snapshot_id)
    assert audit.request_id is None
    assert audit.metadata_["data_type"] == "historical_ohlcv"
    assert audit.metadata_["is_complete"] is False



def test_snapshot_and_audit_share_one_atomic_commit() -> None:
    class FailingSession(FakeSession):
        def commit(self) -> None:
            raise RuntimeError("audit insert failed")

    class FailingFactory:
        def __call__(self) -> FailingSession:
            return FailingSession()

    repository = MarketDataProvenanceRepository(
        cast(sessionmaker[Session], FailingFactory())
    )
    event = PriceEvent(
        symbol="BTCUSDT",
        price=Decimal("95000"),
        market_event_timestamp=NOW,
        received_timestamp=NOW,
        source="binance_spot_rest",
        event_id="atomic-test",
    )
    price = validate_price_event(
        event,
        now=NOW,
        source_healthy=True,
        clock_healthy=True,
    )

    import pytest

    with pytest.raises(RuntimeError, match="audit insert failed"):
        repository.record_price(price, request_id=uuid4())
