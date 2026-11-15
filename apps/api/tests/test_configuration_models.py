"""Tests for Gate 2 configuration model metadata."""

from typing import cast

from sqlalchemy import Table
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import DateTime, Numeric

from app.db.base import Base
from app.db.models import AppSettings, RiskSettings


def _constraint_names(table: Table) -> set[str | None]:
    return {constraint.name for constraint in table.constraints}


def test_application_settings_are_private_singleton_metadata() -> None:
    table = cast(Table, AppSettings.__table__)
    assert table.schema == "baymax"
    assert Base.metadata.tables["baymax.app_settings"] is table
    assert "ck_app_settings_singleton" in _constraint_names(table)
    assert table.columns["timezone"].default is None
    assert table.columns["timezone"].server_default is not None
    assert table.columns["default_currency"].nullable is True
    assert isinstance(table.columns["general_settings"].type, JSONB)


def test_risk_settings_are_private_singleton_and_fail_closed() -> None:
    table = cast(Table, RiskSettings.__table__)
    assert table.schema == "baymax"
    assert Base.metadata.tables["baymax.risk_settings"] is table
    names = _constraint_names(table)
    assert {
        "ck_risk_settings_singleton",
        "ck_risk_settings_trade_risk_pair",
        "ck_risk_settings_trade_risk_range",
        "ck_risk_settings_daily_loss_pair",
        "ck_risk_settings_daily_loss_range",
        "ck_risk_settings_open_positions",
        "ck_risk_settings_leverage",
        "ck_risk_settings_currency_format",
        "ck_risk_settings_quote_currency_required",
        "ck_risk_settings_additional_object",
    }.issubset(names)
    for field in (
        "max_risk_per_trade_value",
        "max_daily_loss_value",
        "max_open_positions",
        "max_leverage",
    ):
        assert table.columns[field].nullable is True
        assert table.columns[field].server_default is None


def test_configuration_timestamps_are_timezone_aware() -> None:
    for model in (AppSettings, RiskSettings):
        table = cast(Table, model.__table__)
        for field in ("created_at", "updated_at"):
            assert isinstance(table.columns[field].type, DateTime)
            assert cast(DateTime, table.columns[field].type).timezone is True


def test_risk_values_use_fixed_precision_numeric_types() -> None:
    table = cast(Table, RiskSettings.__table__)
    assert isinstance(table.columns["max_risk_per_trade_value"].type, Numeric)
    assert isinstance(table.columns["max_daily_loss_value"].type, Numeric)
