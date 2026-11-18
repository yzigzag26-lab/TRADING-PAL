"""Tests for append-only market-data provenance schema metadata."""

from typing import cast

from sqlalchemy import Table
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import DateTime

from app.db.base import Base
from app.db.models import MarketDataSnapshot


def test_market_data_snapshot_is_registered_in_private_schema() -> None:
    assert MarketDataSnapshot.__table__.schema == "baymax"
    assert Base.metadata.tables["baymax.market_data_snapshots"] is MarketDataSnapshot.__table__


def test_market_data_snapshot_has_integrity_constraints() -> None:
    table = cast(Table, MarketDataSnapshot.__table__)
    names = {constraint.name for constraint in table.constraints}
    assert {
        "ck_market_data_snapshots_data_type",
        "ck_market_data_snapshots_validation_state",
        "ck_market_data_snapshots_age_nonnegative",
        "ck_market_data_snapshots_payload_object",
    }.issubset(names)


def test_market_data_snapshot_uses_jsonb_and_timezone_aware_instants() -> None:
    table = cast(Table, MarketDataSnapshot.__table__)
    assert isinstance(table.columns["payload"].type, JSONB)
    for name in ("market_event_timestamp", "received_timestamp", "validated_timestamp"):
        column_type = cast(DateTime, table.columns[name].type)
        assert column_type.timezone is True
