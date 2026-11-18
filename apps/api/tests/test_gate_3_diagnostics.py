from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.api.v1.endpoints.diagnostics import (
    _event_age_ms,
    _snapshot_insert_read_rollback,
)
from app.market_data.models import PriceEvent


def _event(*, age_ms: int = 250) -> PriceEvent:
    now = datetime.now(UTC)
    return PriceEvent(
        symbol="BTCUSDT",
        price=Decimal("65000.00"),
        market_event_timestamp=now - timedelta(milliseconds=age_ms),
        exchange_event_timestamp=now - timedelta(milliseconds=age_ms),
        received_timestamp=now,
        source="binance_spot_websocket",
        event_id="123456",
    )


def test_diagnostic_event_freshness_accepts_recent_positive_trade() -> None:
    assert 0 <= _event_age_ms(_event()) <= 3_000


@pytest.mark.parametrize("age_ms", [3_001, -1_000])
def test_diagnostic_event_freshness_rejects_stale_or_future_trade(age_ms: int) -> None:
    with pytest.raises(ValueError, match="freshness limit"):
        _event_age_ms(_event(age_ms=age_ms))


class _FakeTransaction:
    is_active = True

    def __init__(self) -> None:
        self.rolled_back = False

    def rollback(self) -> None:
        self.rolled_back = True
        self.is_active = False


class _FakeResult:
    def __init__(self, value: UUID) -> None:
        self.value = value

    def scalar_one_or_none(self) -> UUID:
        return self.value


class _FakeSession:
    def __init__(self) -> None:
        self.row = None
        self.transaction = _FakeTransaction()
        self.closed = False

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *_: object) -> None:
        self.closed = True

    def begin(self) -> _FakeTransaction:
        return self.transaction

    def add(self, row: object) -> None:
        self.row = row

    def flush(self) -> None:
        assert self.row is not None
        self.row.id = uuid4()

    def execute(self, _statement: object) -> _FakeResult:
        assert self.row is not None
        return _FakeResult(self.row.id)


class _FakeSessionFactory:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session

    def __call__(self) -> _FakeSession:
        return self.session


def test_snapshot_probe_rolls_back_after_insert_and_read() -> None:
    session = _FakeSession()
    result = _snapshot_insert_read_rollback(
        _FakeSessionFactory(session),  # type: ignore[arg-type]
        "BTCUSDT",
    )

    assert result == {
        "insert_read_verified": True,
        "transaction_rolled_back": True,
        "durable_commit_verified": False,
    }
    assert session.transaction.rolled_back is True
    assert session.closed is True
