"""Persistence boundary for exact market-data provenance snapshots."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from app.db.models.market_data_snapshot import MarketDataSnapshot
from app.market_data.candles import HistoricalCandleSeries
from app.market_data.models import ValidatedPrice


class PriceSnapshotRecorder(Protocol):
    """Minimal repository contract used by current-market orchestration."""

    def record_price(self, price: ValidatedPrice, *, request_id: UUID | None = None) -> UUID: ...


class MarketDataProvenanceRepository:
    """Append-only persistence for validated price and historical-series evidence."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def record_price(
        self,
        price: ValidatedPrice,
        *,
        request_id: UUID | None = None,
    ) -> UUID:
        """Persist a validated current-price snapshot and return its stable ID."""
        row = MarketDataSnapshot(
            exchange=price.exchange,
            market=price.market,
            symbol=price.symbol,
            data_type="trade_price",
            source=price.source,
            market_event_timestamp=price.market_event_timestamp,
            exchange_event_timestamp=price.market_event_timestamp,
            received_timestamp=price.received_timestamp,
            validated_timestamp=price.validated_timestamp,
            age_ms_at_validation=price.age_ms_at_validation,
            connection_state="HEALTHY",
            validation_state="VALIDATED",
            request_id=request_id,
            payload={
                "price": str(price.price),
                "event_id": price.event_id,
            },
        )
        with self._session_factory() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.id

    def record_historical_series(
        self,
        series: HistoricalCandleSeries,
        *,
        request_id: UUID | None = None,
    ) -> UUID:
        """Persist the exact returned candle series, including any unresolved gaps."""
        received = max(
            (candle.received_time for candle in series.candles),
            default=None,
        )
        row = MarketDataSnapshot(
            exchange="BINANCE",
            market="SPOT",
            symbol=series.symbol,
            data_type="historical_ohlcv",
            interval=series.interval,
            source=series.source,
            received_timestamp=received,
            validated_timestamp=datetime.now(UTC),
            connection_state="NOT_APPLICABLE",
            validation_state="VALIDATED" if series.complete else "INCOMPLETE",
            requested_start=series.requested_start,
            requested_end=series.requested_end,
            is_complete=series.complete,
            request_id=request_id,
            payload=series.model_dump(mode="json", exclude={"snapshot_id"}),
        )
        with self._session_factory() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.id
