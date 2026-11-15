"""Singleton risk configuration model with intentionally unset initial limits."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Integer,
    Numeric,
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RiskSettings(Base):
    """Owner-controlled risk limits; NULL means the limit is not configured."""

    __tablename__ = "risk_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_risk_settings_singleton"),
        CheckConstraint(
            "(max_risk_per_trade_value IS NULL AND max_risk_per_trade_unit IS NULL) OR "
            "(max_risk_per_trade_value IS NOT NULL AND "
            "max_risk_per_trade_unit IS NOT NULL)",
            name="ck_risk_settings_trade_risk_pair",
        ),
        CheckConstraint(
            "max_risk_per_trade_value IS NULL OR "
            "(max_risk_per_trade_value > 0 AND "
            "((max_risk_per_trade_unit = 'percent' AND "
            "max_risk_per_trade_value <= 100) "
            "OR max_risk_per_trade_unit = 'quote_currency'))",
            name="ck_risk_settings_trade_risk_range",
        ),
        CheckConstraint(
            "max_risk_per_trade_unit IS NULL OR "
            "max_risk_per_trade_unit IN ('percent', 'quote_currency')",
            name="ck_risk_settings_trade_risk_unit",
        ),
        CheckConstraint(
            "(max_daily_loss_value IS NULL AND max_daily_loss_unit IS NULL) OR "
            "(max_daily_loss_value IS NOT NULL AND max_daily_loss_unit IS NOT NULL)",
            name="ck_risk_settings_daily_loss_pair",
        ),
        CheckConstraint(
            "max_daily_loss_value IS NULL OR "
            "(max_daily_loss_value > 0 AND "
            "((max_daily_loss_unit = 'percent' AND max_daily_loss_value <= 100) "
            "OR max_daily_loss_unit = 'quote_currency'))",
            name="ck_risk_settings_daily_loss_range",
        ),
        CheckConstraint(
            "max_daily_loss_unit IS NULL OR max_daily_loss_unit IN ('percent', 'quote_currency')",
            name="ck_risk_settings_daily_loss_unit",
        ),
        CheckConstraint(
            "max_open_positions IS NULL OR max_open_positions >= 1",
            name="ck_risk_settings_open_positions",
        ),
        CheckConstraint(
            "max_leverage IS NULL OR max_leverage >= 1",
            name="ck_risk_settings_leverage",
        ),
        CheckConstraint(
            "default_risk_currency IS NULL OR default_risk_currency ~ '^[A-Z0-9]{2,12}
        ),
        CheckConstraint(
            "(max_risk_per_trade_unit IS DISTINCT FROM 'quote_currency' "
            "AND max_daily_loss_unit IS DISTINCT FROM 'quote_currency') "
            "OR default_risk_currency IS NOT NULL",
            name="ck_risk_settings_quote_currency_required",
        ),
        CheckConstraint(
            "jsonb_typeof(additional_settings) = 'object'",
            name="ck_risk_settings_additional_object",
        ),
        {"schema": "baymax"},
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, server_default=text("1"))
    max_risk_per_trade_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    max_risk_per_trade_unit: Mapped[str | None] = mapped_column(String(20))
    max_daily_loss_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    max_daily_loss_unit: Mapped[str | None] = mapped_column(String(20))
    max_open_positions: Mapped[int | None] = mapped_column(Integer)
    max_leverage: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    default_risk_currency: Mapped[str | None] = mapped_column(String(12))
    additional_settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
",
            name="ck_risk_settings_currency_format",
        ),
        CheckConstraint(
            "(max_risk_per_trade_unit IS DISTINCT FROM 'quote_currency' "
            "AND max_daily_loss_unit IS DISTINCT FROM 'quote_currency') "
            "OR default_risk_currency IS NOT NULL",
            name="ck_risk_settings_quote_currency_required",
        ),
        CheckConstraint(
            "jsonb_typeof(additional_settings) = 'object'",
            name="ck_risk_settings_additional_object",
        ),
        {"schema": "baymax"},
    )

    id: Mapped[int] = mapped_column(
        SmallInteger, primary_key=True, server_default=text("1")
    )
    max_risk_per_trade_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    max_risk_per_trade_unit: Mapped[str | None] = mapped_column(String(20))
    max_daily_loss_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    max_daily_loss_unit: Mapped[str | None] = mapped_column(String(20))
    max_open_positions: Mapped[int | None] = mapped_column(Integer)
    max_leverage: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    default_risk_currency: Mapped[str | None] = mapped_column(String(12))
    additional_settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
",
            name="ck_risk_settings_currency_format",
        ),
        CheckConstraint(
            "(max_risk_per_trade_unit IS DISTINCT FROM 'quote_currency' "
            "AND max_daily_loss_unit IS DISTINCT FROM 'quote_currency') "
            "OR default_risk_currency IS NOT NULL",
            name="ck_risk_settings_quote_currency_required",
        ),
        CheckConstraint(
            "jsonb_typeof(additional_settings) = 'object'",
            name="ck_risk_settings_additional_object",
        ),
        {"schema": "baymax"},
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, server_default=text("1"))
    max_risk_per_trade_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    max_risk_per_trade_unit: Mapped[str | None] = mapped_column(String(20))
    max_daily_loss_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    max_daily_loss_unit: Mapped[str | None] = mapped_column(String(20))
    max_open_positions: Mapped[int | None] = mapped_column(Integer)
    max_leverage: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    default_risk_currency: Mapped[str | None] = mapped_column(String(12))
    additional_settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
",
            name="ck_risk_settings_currency_format",
        ),
        CheckConstraint(
            "(max_risk_per_trade_unit IS DISTINCT FROM 'quote_currency' "
            "AND max_daily_loss_unit IS DISTINCT FROM 'quote_currency') "
            "OR default_risk_currency IS NOT NULL",
            name="ck_risk_settings_quote_currency_required",
        ),
        CheckConstraint(
            "jsonb_typeof(additional_settings) = 'object'",
            name="ck_risk_settings_additional_object",
        ),
        {"schema": "baymax"},
    )

    id: Mapped[int] = mapped_column(
        SmallInteger, primary_key=True, server_default=text("1")
    )
    max_risk_per_trade_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    max_risk_per_trade_unit: Mapped[str | None] = mapped_column(String(20))
    max_daily_loss_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    max_daily_loss_unit: Mapped[str | None] = mapped_column(String(20))
    max_open_positions: Mapped[int | None] = mapped_column(Integer)
    max_leverage: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    default_risk_currency: Mapped[str | None] = mapped_column(String(12))
    additional_settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
