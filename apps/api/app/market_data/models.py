"""Canonical, validated market-data domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PriceEvent(BaseModel):
    """A Binance Spot price event with its source timestamp preserved."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    exchange: Literal["BINANCE"] = "BINANCE"
    market: Literal["SPOT"] = "SPOT"
    symbol: str = Field(min_length=1, max_length=30)
    price: Decimal
    market_event_timestamp: datetime
    exchange_event_timestamp: datetime | None = None
    received_timestamp: datetime
    source: Literal["binance_spot_websocket", "binance_spot_rest"]
    event_id: str | None = None

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized.isalnum():
            raise ValueError("symbol must contain only letters and digits")
        return normalized

    @field_validator("price", mode="before")
    @classmethod
    def parse_price(cls, value: object) -> Decimal:
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("price must be a valid decimal") from exc
        if not parsed.is_finite() or parsed <= 0:
            raise ValueError("price must be finite and greater than zero")
        return parsed

    @field_validator("market_event_timestamp", "exchange_event_timestamp", "received_timestamp")
    @classmethod
    def require_aware_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(UTC)


class ValidatedPrice(BaseModel):
    """Price snapshot accepted by the Gate 3 freshness boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    exchange: Literal["BINANCE"]
    market: Literal["SPOT"]
    symbol: str
    price: Decimal
    market_event_timestamp: datetime
    exchange_event_timestamp: datetime | None = None
    received_timestamp: datetime
    validated_timestamp: datetime
    age_ms_at_validation: int = Field(ge=0)
    source: Literal["binance_spot_websocket", "binance_spot_rest"]
    event_id: str | None = None
