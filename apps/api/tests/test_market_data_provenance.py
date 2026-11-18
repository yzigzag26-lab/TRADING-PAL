"""Tests for persistent market-data provenance payload construction."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy.orm import Session, sessionmaker

from app.market_data.candles import HistoricalCandle, HistoricalCandleSeries, interval_close_time
from app.market_data.freshness import validate_price_event
from app.market_data.models import PriceEvent
from app.market_data.provenance import MarketDataProvenanceRepository

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)


class FakeSession:
    def __init__(self) -> None:
        self.row: object | None = None

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def add(self, row: object) -> None:
        self.row = row

    def commit(self) -> None:
        if self.row is not None:
            setattr(self.row, "id", uuid4())

    def refresh(self, row: object) -> None:
        assert row is self.row


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
    row = factory.session.row

    assert isinstance(snapshot_id, UUID)
    assert row is not None
    assert getattr(row, "data_type") == "trade_price"
    assert getattr(row, "market_event_timestamp") == event.market_event_timestamp
    assert getattr(row, "exchange_event_timestamp") == event.exchange_event_timestamp
    assert getattr(row, "age_ms_at_validation") == 300
    assert getattr(row, "request_id") == request_id
    assert getattr(row, "payload") == {"price": "95000.12345678", "event_id": "12345"}
    assert getattr(row, "connection_state") == "WEBSOCKET_HEALTHY"


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
    row = factory.session.row

    assert isinstance(snapshot_id, UUID)
    assert row is not None
    assert getattr(row, "data_type") == "historical_ohlcv"
    assert getattr(row, "is_complete") is False
    assert getattr(row, "validation_state") == "INCOMPLETE"
    assert getattr(row, "payload")["missing_open_times"] == [missing.isoformat().replace("+00:00", "Z")]
    assert len(getattr(row, "payload")["candles"]) == 1
