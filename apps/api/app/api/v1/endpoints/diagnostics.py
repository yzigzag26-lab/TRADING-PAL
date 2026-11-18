"""Owner-only production diagnostics for Gate 3 market-data infrastructure.

The endpoint performs bounded, read-only exchange checks. Its database probe
uses an INSERT + SELECT inside a transaction that is always rolled back, so it
does not create a permanent row in the append-only production table.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Literal, cast

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.security import SESSION_COOKIE_NAME, verify_session_token
from app.core.clock_health import ClockHealthMonitor
from app.core.config import Settings
from app.db.models.market_data_snapshot import MarketDataSnapshot
from app.market_data.binance_rest import BinanceSpotRestClient
from app.market_data.binance_stream import BinanceSpotTradeStream
from app.market_data.models import PriceEvent

router = APIRouter(prefix="/diagnostics", tags=["Diagnostics"])

DIAGNOSTIC_SYMBOL = "BTCUSDT"
REST_TIMEOUT_SECONDS = 8.0
WEBSOCKET_EVENT_TIMEOUT_SECONDS = 10.0
MAX_DIAGNOSTIC_EVENT_AGE_MS = 3_000


class DiagnosticCheck(BaseModel):
    """One bounded infrastructure check."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["passed", "failed"]
    duration_ms: int
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Gate3DiagnosticResponse(BaseModel):
    """Sanitized result of a single production diagnostic run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["passed", "failed"]
    checked_at: datetime
    symbol: str
    checks: dict[str, DiagnosticCheck]
    snapshot_write_mode: Literal["transaction_rolled_back"]


def _require_owner(request: Request) -> Settings:
    settings = cast(Settings, request.app.state.settings)
    if not verify_session_token(
        request.cookies.get(SESSION_COOKIE_NAME),
        settings.session_secret,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
        )
    return settings


def _event_age_ms(event: PriceEvent, *, now: datetime | None = None) -> int:
    """Return event age; reject future-dated or stale diagnostic events."""
    current = now or datetime.now(UTC)
    age_ms = int((current - event.market_event_timestamp).total_seconds() * 1000)
    if age_ms < 0 or age_ms > MAX_DIAGNOSTIC_EVENT_AGE_MS:
        raise ValueError("Market event timestamp is outside the diagnostic freshness limit")
    if event.price <= 0:
        raise ValueError("Market event price must be positive")
    return age_ms


def _snapshot_insert_read_rollback(
    session_factory: sessionmaker[Session],
    symbol: str,
) -> dict[str, Any]:
    """Verify runtime INSERT and SELECT privileges without committing evidence."""
    with session_factory() as session:
        transaction = session.begin()
        try:
            row = MarketDataSnapshot(
                exchange="BINANCE",
                market="SPOT",
                symbol=symbol,
                data_type="trade_price",
                source="gate3_diagnostic",
                validated_timestamp=datetime.now(UTC),
                connection_state="DIAGNOSTIC",
                validation_state="VALIDATED",
                payload={
                    "diagnostic": True,
                    "purpose": "gate_3_insert_read_rollback",
                },
            )
            session.add(row)
            session.flush()
            snapshot_id = row.id
            persisted_id = session.execute(
                select(MarketDataSnapshot.id).where(MarketDataSnapshot.id == snapshot_id)
            ).scalar_one_or_none()
            if persisted_id != snapshot_id:
                raise RuntimeError("Inserted diagnostic snapshot could not be read back")
        finally:
            if transaction.is_active:
                transaction.rollback()

    return {
        "insert_read_verified": True,
        "transaction_rolled_back": True,
        "durable_commit_verified": False,
    }


async def _read_one_websocket_event(symbol: str) -> PriceEvent:
    """Open a fresh public stream, receive one trade, and close that connection."""
    stream = BinanceSpotTradeStream()
    iterator = stream.listen(symbol)
    try:
        event = await asyncio.wait_for(
            anext(iterator),
            timeout=WEBSOCKET_EVENT_TIMEOUT_SECONDS,
        )
        _event_age_ms(event)
        if event.symbol.upper() != symbol:
            raise ValueError("WebSocket returned a different market symbol")
        return event
    finally:
        await iterator.aclose()


async def _timed_check(
    name: str,
    operation: Callable[[], Awaitable[dict[str, Any]]],
) -> DiagnosticCheck:
    started = perf_counter()
    try:
        metadata = await operation()
        return DiagnosticCheck(
            status="passed",
            duration_ms=round((perf_counter() - started) * 1000),
            message=f"{name} check passed.",
            metadata=metadata,
        )
    except Exception as exc:
        return DiagnosticCheck(
            status="failed",
            duration_ms=round((perf_counter() - started) * 1000),
            message=f"{name} check failed ({type(exc).__name__}).",
        )


@router.post(
    "/gate-3",
    response_model=Gate3DiagnosticResponse,
    summary="Run production Gate 3 diagnostics",
    description=(
        "Owner-only live checks for NTP clock consensus, Binance Spot REST, "
        "WebSocket reconnect capability, and transactional snapshot INSERT/SELECT. "
        "The snapshot probe is rolled back and never commits a production row."
    ),
)
async def run_gate_3_diagnostics(
    request: Request,
    response: Response,
) -> Gate3DiagnosticResponse:
    """Run bounded diagnostics inside the deployed API process."""
    _require_owner(request)
    symbol = DIAGNOSTIC_SYMBOL

    async def check_clock() -> dict[str, Any]:
        monitor = cast(
            ClockHealthMonitor | None,
            getattr(request.app.state, "clock_health_monitor", None),
        )
        if monitor is None:
            raise RuntimeError("Production NTP monitor is not running")
        snapshot = await monitor.check_once()
        if not snapshot.healthy:
            raise RuntimeError(snapshot.reason)
        return {
            "healthy": snapshot.healthy,
            "healthy_sources": snapshot.healthy_sources,
            "offset_seconds": snapshot.offset_seconds,
            "checked_at": snapshot.checked_at.isoformat() if snapshot.checked_at else None,
        }

    clock_check = await _timed_check("NTP clock", check_clock)

    async def check_rest() -> dict[str, Any]:
        async with BinanceSpotRestClient() as client:
            event = await asyncio.wait_for(
                client.latest_trade(symbol),
                timeout=REST_TIMEOUT_SECONDS,
            )
        age_ms = _event_age_ms(event)
        return {
            "symbol": event.symbol,
            "source": event.source,
            "event_age_ms": age_ms,
            "trade_id_present": event.event_id is not None,
        }

    async def check_websocket_recovery() -> dict[str, Any]:
        # Two independent subscriptions prove that a closed stream can be
        # re-established and deliver a fresh trade from the deployed runtime.
        first = await _read_one_websocket_event(symbol)
        second = await _read_one_websocket_event(symbol)
        return {
            "symbol": symbol,
            "connections_established": 2,
            "first_trade_id_present": first.event_id is not None,
            "second_trade_id_present": second.event_id is not None,
            "reconnected_after_close": True,
        }

    async def check_snapshot() -> dict[str, Any]:
        factory = cast(
            sessionmaker[Session] | None,
            getattr(request.app.state, "db_session_factory", None),
        )
        if factory is None:
            raise RuntimeError("Runtime database session factory is not configured")
        return await asyncio.to_thread(_snapshot_insert_read_rollback, factory, symbol)

    rest_check, websocket_check, snapshot_check = await asyncio.gather(
        _timed_check("Binance Spot REST", check_rest),
        _timed_check("Binance WebSocket reconnect", check_websocket_recovery),
        _timed_check("Snapshot transactional INSERT/SELECT", check_snapshot),
    )

    checks = {
        "ntp_clock": clock_check,
        "binance_spot_rest": rest_check,
        "websocket_reconnect": websocket_check,
        "snapshot_insert_read_rollback": snapshot_check,
    }
    overall_status: Literal["passed", "failed"] = (
        "passed" if all(check.status == "passed" for check in checks.values()) else "failed"
    )
    response.status_code = (
        status.HTTP_200_OK if overall_status == "passed" else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return Gate3DiagnosticResponse(
        status=overall_status,
        checked_at=datetime.now(UTC),
        symbol=symbol,
        checks=checks,
        snapshot_write_mode="transaction_rolled_back",
    )
