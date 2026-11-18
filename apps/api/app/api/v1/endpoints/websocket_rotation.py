"""Owner-only forced short-rotation diagnostic for the live market-data service."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from time import monotonic, perf_counter
from typing import Any, Literal, cast

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict

from app.auth.security import SESSION_COOKIE_NAME, verify_session_token
from app.core.config import Settings
from app.market_data.binance_stream import BinanceSpotTradeStream
from app.market_data.models import PriceEvent
from app.market_data.service import BinanceMarketDataService

router = APIRouter(prefix="/diagnostics/gate-3", tags=["Diagnostics"])

ROTATION_TEST_LIFETIME_SECONDS = 5.0
ROTATION_TEST_TIMEOUT_SECONDS = 45.0
ROTATION_TEST_SYMBOL = "BTCUSDT"


class RotationDiagnosticResponse(BaseModel):
    """Bounded evidence from one isolated real-service rotation test."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["passed", "failed"]
    checked_at: datetime
    symbol: str
    forced_connection_lifetime_seconds: float
    checks: dict[str, dict[str, Any]]


class _ObservedRotationStream:
    """Use the real Binance stream while recording its connection callbacks."""

    def __init__(self) -> None:
        self._stream = BinanceSpotTradeStream(
            connection_lifetime_seconds=ROTATION_TEST_LIFETIME_SECONDS
        )
        self.transitions: list[tuple[bool, float]] = []

    async def listen(
        self,
        symbol: str,
        *,
        on_connection_state: Callable[[bool], Awaitable[None]],
    ) -> AsyncIterator[PriceEvent]:
        async def observe(connected: bool) -> None:
            self.transitions.append((connected, monotonic()))
            await on_connection_state(connected)

        async for event in self._stream.listen(symbol, on_connection_state=observe):
            yield event


def _require_owner(request: Request) -> None:
    settings = cast(Settings, request.app.state.settings)
    if not verify_session_token(
        request.cookies.get(SESSION_COOKIE_NAME),
        settings.session_secret,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
        )


async def _wait_until(
    predicate: Callable[[], bool],
    *,
    timeout_seconds: float,
    description: str,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(f"Timed out waiting for {description}")
        await asyncio.sleep(0.05)


async def _run_rotation_test(clock_healthy: bool) -> dict[str, Any]:
    if not clock_healthy:
        raise RuntimeError("Production clock-health monitor is not healthy")

    observed_stream = _ObservedRotationStream()
    service = BinanceMarketDataService(stream=observed_stream)
    started_at = perf_counter()
    lifecycle_started_at = monotonic()
    initial_event_id: str | None = None

    try:
        await service.start()
        await service.start_symbol_stream(ROTATION_TEST_SYMBOL)

        await _wait_until(
            lambda: (
                service.stream_status(ROTATION_TEST_SYMBOL)["healthy"] is True
                and service.stream_status(ROTATION_TEST_SYMBOL)["event_source"]
                == "binance_spot_websocket"
            ),
            timeout_seconds=10.0,
            description="first healthy WebSocket trade",
        )
        initial_status = service.stream_status(ROTATION_TEST_SYMBOL)
        initial_event_id = cast(str | None, initial_status["event_id"])
        if initial_event_id is None:
            raise RuntimeError("Initial WebSocket trade did not contain a trade ID")

        await _wait_until(
            lambda: any(not connected for connected, _ in observed_stream.transitions),
            timeout_seconds=12.0,
            description="forced connection close",
        )
        await _wait_until(
            lambda: sum(connected for connected, _ in observed_stream.transitions) >= 2,
            timeout_seconds=12.0,
            description="replacement WebSocket subscription",
        )
        first_connected_at = next(
            timestamp
            for connected, timestamp in observed_stream.transitions
            if connected
        )
        first_disconnected_at = next(
            timestamp
            for connected, timestamp in observed_stream.transitions
            if not connected
        )
        rotation_elapsed_seconds = first_disconnected_at - first_connected_at
        if rotation_elapsed_seconds < ROTATION_TEST_LIFETIME_SECONDS - 0.1:
            raise RuntimeError("WebSocket closed before the forced rotation deadline")

        await _wait_until(
            lambda: (
                service.stream_status(ROTATION_TEST_SYMBOL)["connected"] is True
                and service.stream_status(ROTATION_TEST_SYMBOL)["healthy"] is True
                and service.stream_status(ROTATION_TEST_SYMBOL)["event_source"]
                == "binance_spot_websocket"
                and service.stream_status(ROTATION_TEST_SYMBOL)["event_id"]
                != initial_event_id
            ),
            timeout_seconds=12.0,
            description="fresh WebSocket trade accepted after reconnection",
        )

        validated = await service.get_current_price(
            ROTATION_TEST_SYMBOL,
            clock_healthy=clock_healthy,
        )
        if validated.source != "binance_spot_websocket":
            raise RuntimeError(
                "Post-reconnect consume-time validation did not use a WebSocket event"
            )
        if validated.event_id is None or validated.event_id == initial_event_id:
            raise RuntimeError("Post-reconnect validation did not advance the trade ID")

        return {
            "initial_connection_trade_id": initial_event_id,
            "connection_transitions": [
                {
                    "connected": connected,
                    "elapsed_since_start_ms": round((timestamp - lifecycle_started_at) * 1000),
                }
                for connected, timestamp in observed_stream.transitions
            ],
            "rotation_elapsed_seconds": round(rotation_elapsed_seconds, 3),
            "disconnect_observed": any(
                not connected for connected, _ in observed_stream.transitions
            ),
            "resubscription_observed": sum(
                connected for connected, _ in observed_stream.transitions
            ) >= 2,
            "post_reconnect_trade_id": validated.event_id,
            "post_reconnect_source": validated.source,
            "post_reconnect_age_ms": validated.age_ms_at_validation,
            "post_reconnect_price": str(validated.price),
            "consume_time_validation": "passed",
            "duration_ms": round((perf_counter() - started_at) * 1000),
        }
    finally:
        await asyncio.wait_for(service.close(), timeout=5.0)


@router.post(
    "/websocket-rotation",
    response_model=RotationDiagnosticResponse,
    summary="Verify production WebSocket rotation and service recovery",
    description=(
        "Owner-only, read-only live test. Starts an isolated BinanceMarketDataService "
        "using the real public Binance REST and WebSocket clients, forces a five-second "
        "connection lifetime, verifies close/resubscription, and validates a fresh "
        "post-reconnect WebSocket trade. The application's normal stream and rotation "
        "setting are not modified. No database snapshot is written."
    ),
)
async def verify_websocket_rotation(
    request: Request,
    response: Response,
) -> RotationDiagnosticResponse:
    """Exercise forced rotation through a separate real market-data service."""
    _require_owner(request)
    clock_provider = cast(Callable[[], bool], request.app.state.clock_health_provider)
    clock_healthy = clock_provider()

    try:
        result = await asyncio.wait_for(
            _run_rotation_test(clock_healthy),
            timeout=ROTATION_TEST_TIMEOUT_SECONDS,
        )
        checks = {
            "initial_websocket_trade": {
                "status": "passed",
                "trade_id_present": result["initial_connection_trade_id"] is not None,
            },
            "forced_disconnect": {
                "status": "passed" if result["disconnect_observed"] else "failed",
                "observed": result["disconnect_observed"],
            },
            "resubscription": {
                "status": "passed" if result["resubscription_observed"] else "failed",
                "connection_count": sum(
                    transition["connected"] for transition in result["connection_transitions"]
                ),
                "first_connection_lifetime_seconds": result["rotation_elapsed_seconds"],
            },
            "fresh_post_reconnect_trade": {
                "status": "passed",
                "source": result["post_reconnect_source"],
                "trade_id": result["post_reconnect_trade_id"],
                "age_ms": result["post_reconnect_age_ms"],
                "price": result["post_reconnect_price"],
                "consume_time_validation": result["consume_time_validation"],
            },
        }
        response.status_code = status.HTTP_200_OK
        overall: Literal["passed", "failed"] = "passed"
    except Exception as exc:
        checks = {
            "forced_rotation_lifecycle": {
                "status": "failed",
                "reason": type(exc).__name__,
                "message": str(exc)[:240],
            }
        }
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        overall = "failed"

    return RotationDiagnosticResponse(
        status=overall,
        checked_at=datetime.now(UTC),
        symbol=ROTATION_TEST_SYMBOL,
        forced_connection_lifetime_seconds=ROTATION_TEST_LIFETIME_SECONDS,
        checks=checks,
    )
