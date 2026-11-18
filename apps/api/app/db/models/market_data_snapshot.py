"""Append-only provenance snapshots for validated market data."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MarketDataSnapshot(Base):
    """Immutable record tying a validated market input to its exact source data."""

    __tablename__ = "market_data_snapshots"
    __table_args__ = (
        CheckConstraint(
            "data_type IN ('trade_price', 'historical_ohlcv')",
            name="ck_market_data_snapshots_data_type",
        ),
        CheckConstraint(
            "validation_state IN ('VALIDATED', 'INCOMPLETE')",
            name="ck_market_data_snapshots_validation_state",
        ),
        CheckConstraint(
            "age_ms_at_validation IS NULL OR age_ms_at_validation >= 0",
            name="ck_market_data_snapshots_age_nonnegative",
        ),
        CheckConstraint(
            "jsonb_typeof(payload) = 'object'",
            name="ck_market_data_snapshots_payload_object",
        ),
        Index(
            "ix_market_data_snapshots_symbol_created",
            "symbol",
            text("created_at DESC"),
        ),
        Index(
            "ix_market_data_snapshots_type_created",
            "data_type",
            text("created_at DESC"),
        ),
        {"schema": "baymax"},
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    exchange: Mapped[str] = mapped_column(Text, nullable=False)
    market: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    data_type: Mapped[str] = mapped_column(Text, nullable=False)
    interval: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    market_event_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exchange_event_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validated_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    age_ms_at_validation: Mapped[int | None] = mapped_column(Integer)
    connection_state: Mapped[str] = mapped_column(Text, nullable=False)
    validation_state: Mapped[str] = mapped_column(Text, nullable=False)
    requested_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_complete: Mapped[bool | None] = mapped_column(Boolean)
    request_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
