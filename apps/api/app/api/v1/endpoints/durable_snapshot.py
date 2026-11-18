"""Owner-only durable snapshot persistence verification."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.security import SESSION_COOKIE_NAME, verify_session_token
from app.core.config import Settings
from app.db.models.market_data_snapshot import MarketDataSnapshot
from app.market_data.models import ValidatedPrice
from app.orchestration.requests import (
    AnalysisInputUnavailable,
    AnalysisRequest,
    BaymaxRequestOrchestrator,
)

router = APIRouter(prefix="/diagnostics/gate-3", tags=["Diagnostics"])


class DurableSnapshotVerificationRequest(BaseModel):
    """Require an explicit acknowledgement before creating a permanent row."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    confirm_durable_write: Literal[True]


class DurableSnapshotVerificationResponse(BaseModel):
    """Evidence that a committed snapshot is visible from a new transaction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["passed"]
    durable_commit_verified: Literal[True]
    separate_transaction_readback: Literal[True]
    snapshot_id: UUID
    request_id: UUID
    exchange: Literal["BINANCE"]
    market: Literal["SPOT"]
    symbol: str
    data_type: Literal["trade_price"]
    source: str
    price: str
    event_id: str | None
    market_event_timestamp: datetime
    exchange_event_timestamp: datetime | None
    received_timestamp: datetime
    validated_timestamp: datetime
    age_ms_at_validation: int
    created_at: datetime


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


def _verify_committed_snapshot_in_new_transaction(
    session_factory: sessionmaker[Session],
    snapshot_id: UUID,
    expected: ValidatedPrice,
) -> dict[str, Any]:
    """Read and compare a committed snapshot using a fresh SQLAlchemy session."""
    with session_factory() as session:
        with session.begin():
            row = session.execute(
                select(MarketDataSnapshot).where(MarketDataSnapshot.id == snapshot_id)
            ).scalar_one_or_none()
            if row is None:
                raise RuntimeError("Committed snapshot was not visible in a new transaction")

            expected_connection_state = (
                "WEBSOCKET_HEALTHY"
                if expected.source == "binance_spot_websocket"
                else "REST_RECOVERY"
            )
            actual = {
                "exchange": row.exchange,
                "market": row.market,
                "symbol": row.symbol,
                "data_type": row.data_type,
                "source": row.source,
                "market_event_timestamp": row.market_event_timestamp,
                "exchange_event_timestamp": row.exchange_event_timestamp,
                "received_timestamp": row.received_timestamp,
                "validated_timestamp": row.validated_timestamp,
                "age_ms_at_validation": row.age_ms_at_validation,
                "connection_state": row.connection_state,
                "validation_state": row.validation_state,
                "payload": row.payload,
                "created_at": row.created_at,
            }
            expected_values = {
                "exchange": expected.exchange,
                "market": expected.market,
                "symbol": expected.symbol,
                "data_type": "trade_price",
                "source": expected.source,
                "market_event_timestamp": expected.market_event_timestamp,
                "exchange_event_timestamp": expected.exchange_event_timestamp,
                "received_timestamp": expected.received_timestamp,
                "validated_timestamp": expected.validated_timestamp,
                "age_ms_at_validation": expected.age_ms_at_validation,
                "connection_state": expected_connection_state,
                "validation_state": "VALIDATED",
                "payload": {
                    "price": str(expected.price),
                    "event_id": expected.event_id,
                },
            }
            if any(actual[key] != value for key, value in expected_values.items()):
                raise RuntimeError("Committed snapshot fields did not match validated market data")
            created_at = actual["created_at"]
            if not isinstance(created_at, datetime) or created_at.tzinfo is None:
                raise RuntimeError("Committed snapshot creation timestamp is missing or invalid")

            return {
                "snapshot_id": row.id,
                "exchange": row.exchange,
                "market": row.market,
                "symbol": row.symbol,
                "data_type": row.data_type,
                "source": row.source,
                "price": str(row.payload["price"]),
                "event_id": row.payload["event_id"],
                "market_event_timestamp": row.market_event_timestamp,
                "exchange_event_timestamp": row.exchange_event_timestamp,
                "received_timestamp": row.received_timestamp,
                "validated_timestamp": row.validated_timestamp,
                "age_ms_at_validation": row.age_ms_at_validation,
                "created_at": row.created_at,
            }


@router.post(
    "/durable-snapshot",
    response_model=DurableSnapshotVerificationResponse,
    summary="Verify one durable BTCUSDT market snapshot",
    description=(
        "Owner-only production write test. Requires confirm_durable_write=true. "
        "Retrieves fresh BTCUSDT data through the normal market-data orchestrator, "
        "commits through the existing provenance repository, then verifies the "
        "same row in a separate database session and transaction. Every successful "
        "invocation creates one permanent append-only audit snapshot."
    ),
)
async def verify_durable_snapshot(
    payload: DurableSnapshotVerificationRequest,
    request: Request,
) -> DurableSnapshotVerificationResponse:
    """Persist one real validated BTCUSDT price and independently read it back."""
    _require_owner(request)
    factory = cast(
        sessionmaker[Session] | None,
        getattr(request.app.state, "db_session_factory", None),
    )
    repository = getattr(request.app.state, "market_data_provenance_repository", None)
    if factory is None or repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Production market-data persistence is not configured.",
        )

    orchestrator = BaymaxRequestOrchestrator(
        request.app.state.market_data_service,
        clock_health_provider=request.app.state.clock_health_provider,
        provenance_repository=repository,
        require_provenance=True,
    )
    request_id = UUID(request.state.request_id)
    try:
        prepared = await orchestrator.prepare(
            AnalysisRequest(
                message="Verify durable market-data snapshot persistence.",
                intent="current_market",
                symbol="BTCUSDT",
            ),
            request_id=request_id,
        )
    except AnalysisInputUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Fresh BTCUSDT data could not be validated and persisted.",
        ) from exc

    if prepared.current_price is None or prepared.market_snapshot_id is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The market-data pipeline did not return a persisted snapshot.",
        )

    try:
        verified = await asyncio.to_thread(
            _verify_committed_snapshot_in_new_transaction,
            factory,
            prepared.market_snapshot_id,
            prepared.current_price,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The snapshot was submitted to the commit path, but independent "
                "database read-back verification failed. Inspect the database before retrying."
            ),
        ) from exc

    return DurableSnapshotVerificationResponse(
        status="passed",
        durable_commit_verified=True,
        separate_transaction_readback=True,
        request_id=request_id,
        **verified,
    )
