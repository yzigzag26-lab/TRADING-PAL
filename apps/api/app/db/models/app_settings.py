"""Singleton application-wide settings model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, SmallInteger, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AppSettings(Base):
    """Owner-controlled defaults shared by the private Baymax instance."""

    __tablename__ = "app_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_app_settings_singleton"),
        CheckConstraint("length(btrim(timezone)) > 0", name="ck_app_settings_timezone_nonempty"),
        CheckConstraint(
            "default_currency IS NULL OR default_currency ~ '^[A-Z0-9]{2,12}$'",
            name="ck_app_settings_currency_format",
        ),
        CheckConstraint(
            "length(btrim(default_exchange)) > 0",
            name="ck_app_settings_exchange_nonempty",
        ),
        CheckConstraint(
            "jsonb_typeof(general_settings) = 'object'",
            name="ck_app_settings_general_object",
        ),
        {"schema": "baymax"},
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, server_default=text("1"))
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'UTC'")
    )
    default_currency: Mapped[str | None] = mapped_column(String(12), nullable=True)
    default_exchange: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'BINANCE'")
    )
    general_settings: Mapped[dict[str, Any]] = mapped_column(
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
