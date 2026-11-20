"""Typed contracts for deterministic setup and risk-scenario analysis."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Decision = Literal["BUY", "SELL", "WAIT"]
BiasDirection = Literal["bullish", "bearish", "neutral"]


class PriceLevel(BaseModel):
    """A single deterministic price level with its derivation method."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    price: Decimal
    method: str = Field(min_length=1, max_length=200)


class EntryZone(BaseModel):
    """Entry zone bounded by deterministic support/resistance evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lower: Decimal
    upper: Decimal
    method: str = Field(min_length=1, max_length=200)


class Scenario(BaseModel):
    """Deterministic trade scenario; every level cites its derivation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: Decision
    direction: BiasDirection
    entry_zone: EntryZone
    stop_loss: PriceLevel
    take_profit_1: PriceLevel
    take_profit_2: PriceLevel | None = None
    risk_distance: Decimal = Field(gt=0)
    reward_distance: Decimal = Field(gt=0)
    risk_reward_ratio: Decimal = Field(gt=0)
    invalidation: str = Field(min_length=1, max_length=500)
    methodology: str = Field(min_length=1, max_length=200)


class StrategyOutcome(BaseModel):
    """Result of deterministic setup evaluation before the safety gate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    proposed_decision: Decision
    direction: BiasDirection
    scenario: Scenario | None = None
    reasons: tuple[str, ...] = ()
    blocking_reasons: tuple[str, ...] = ()


class SafetyResult(BaseModel):
    """Final fail-closed decision after all safety checks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: Decision
    scenario: Scenario | None = None
    blocked: bool
    block_reasons: tuple[str, ...] = ()
    checks: tuple[str, ...] = ()


__all__ = [
    "BiasDirection",
    "Decision",
    "EntryZone",
    "PriceLevel",
    "SafetyResult",
    "Scenario",
    "StrategyOutcome",
]
