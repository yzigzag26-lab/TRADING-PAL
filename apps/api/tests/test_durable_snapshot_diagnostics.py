from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.api.v1.endpoints.durable_snapshot import (
    _verify_committed_snapshot_in_new_transaction,
)
from app.db.models.market_data_snapshot import MarketDataSnapshot
from app.market_data.models import ValidatedPrice

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)


class _Result:
    def __init__(self, row: MarketDataSnapshot | None) -> None:
        self.row = row

    def scalar_one_or_none(self) -> MarketDataSnapshot | None:
        return self.row


class _Transaction:
    def __enter__(self) -> _Transaction:
        return self

    def __exit__(self, *_: object) -> None:
        return None


class _Session:
    def __init__(self, row: MarketDataSnapshot | None) -> None:
        self.row = row
        self.closed = False
        self.transaction = _Transaction()

    def __enter__(self) -> _Session:
        return self

    def __exit__(self, *_: object) -> None:
        self.closed = True

    def begin(self) -> _Transaction:
        return self.transaction

    def execute(self, _statement: object) -> _Result:
        return _Result(self.row)


class _SessionFactory:
    def __init__(self, row: MarketDataSnapshot | None) -> None:
        self.row = row
        self.sessions: list[_Session] = []

    def __call__(self) -> _Session:
        session = _Session(self.row)
        self.sessions.append(session)
        return session


def _validated_price() -> ValidatedPrice:
    return ValidatedPrice(
        exchange="BINANCE",
        market="SPOT",
        symbol="BTCUSDT",
        price=Decimal("95000.12345678"),
        market_event_timestamp=NOW - timedelta(milliseconds=300),
        exchange_event_timestamp=NOW - timedelta(milliseconds=250),
        received_timestamp=NOW - timedelta(milliseconds=100),
        validated_timestamp=NOW,
        age_ms_at_validation=300,
        source="binance_spot_websocket",
        event_id="12345",
    )


def _persisted_row(price: ValidatedPrice) -> MarketDataSnapshot:
    return MarketDataSnapshot(
        id=uuid4(),
        exchange=price.exchange,
        market=price.market,
        symbol=price.symbol,
        data_type="trade_price",
        source=price.source,
        market_event_timestamp=price.market_event_timestamp,
        exchange_event_timestamp=price.exchange_event_timestamp,
        received_timestamp=price.received_timestamp,
        validated_timestamp=price.validated_timestamp,
        age_ms_at_validation=price.age_ms_at_validation,
        connection_state="WEBSOCKET_HEALTHY",
        validation_state="VALIDATED",
        payload={"price": str(price.price), "event_id": price.event_id},
        created_at=NOW + timedelta(milliseconds=5),
    )


def test_durable_snapshot_readback_uses_a_new_transaction_and_verifies_fields() -> None:
    price = _validated_price()
    row = _persisted_row(price)
    factory = _SessionFactory(row)

    result = _verify_committed_snapshot_in_new_transaction(
        factory,  # type: ignore[arg-type]
        row.id,
        price,
    )

    assert result["snapshot_id"] == row.id
    assert result["symbol"] == "BTCUSDT"
    assert result["price"] == "95000.12345678"
    assert result["market_event_timestamp"] == price.market_event_timestamp
    assert result["received_timestamp"] == price.received_timestamp
    assert result["validated_timestamp"] == price.validated_timestamp
    assert result["created_at"] == row.created_at
    assert len(factory.sessions) == 1
    assert factory.sessions[0].closed is True


def test_durable_snapshot_readback_fails_when_committed_row_is_missing() -> None:
    price = _validated_price()
    factory = _SessionFactory(None)

    with pytest.raises(RuntimeError, match="not visible"):
        _verify_committed_snapshot_in_new_transaction(
            factory,  # type: ignore[arg-type]
            uuid4(),
            price,
        )


def test_durable_snapshot_readback_fails_when_payload_does_not_match() -> None:
    price = _validated_price()
    row = _persisted_row(price)
    row.payload = {"price": "1", "event_id": price.event_id}
    factory = _SessionFactory(row)

    with pytest.raises(RuntimeError, match="did not match"):
        _verify_committed_snapshot_in_new_transaction(
            factory,  # type: ignore[arg-type]
            row.id,
            price,
        )
