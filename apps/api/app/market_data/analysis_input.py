"""Gate 4 market-data preparation for intelligence analysis.

Assembles a verified input bundle — fresh ``ValidatedPrice`` plus one
validated, closed-candle ``HistoricalCandleSeries`` per analysis timeframe —
reusing the Gate 3 market-data services, freshness policy, candle validation
and provenance repository. No second candle downloader is introduced.
"""

from __future__ import annotations

import asyncio
from time import perf_counter
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.intelligence.analyzer import (
    ANALYSIS_TIMEFRAMES,
    MarketIntelligenceInput,
    TimeframeSeriesInput,
)
from app.market_data.candles import INTERVALS
from app.market_data.freshness import MarketDataUnavailable
from app.market_data.historical_service import BinanceHistoricalCandleService
from app.market_data.provenance import MarketDataProvenanceRepository
from app.orchestration.requests import PreparedAnalysisInput

# Bounded candle budget per timeframe: comfortably above the longest
# indicator warm-up (~50) and swing-confirmation needs while keeping each
# request to a single kline page per timeframe.
CANDLES_PER_TIMEFRAME = 300
MAX_CANDLE_LIMIT = 1_000


class MarketIntelligenceInputUnavailable(Exception):
    """Raised when required verified inputs cannot be assembled safely."""


def _interval_seconds(interval: str) -> int:
    """Fixed-second interval length; analysis timeframes are all fixed-length."""
    units = {"m": 60, "h": 3600, "d": 86400}
    suffix = interval[-1]
    if suffix not in units or interval.endswith("M") or interval.endswith("w"):
        raise ValueError("Analysis intervals must be fixed-length m/h/d intervals")
    return int(interval[:-1]) * units[suffix]


def closed_window(
    interval: str,
    *,
    count: int,
    now: datetime,
) -> tuple[datetime, datetime]:
    """Return the aligned ``[start, end]`` open boundaries covering ``count``
    fully closed candles ending before ``now``.

    The candle that opened at the current interval boundary is still forming,
    so the requested range ends one full interval earlier.
    """
    if interval not in INTERVALS:
        raise ValueError("Unsupported Binance kline interval")
    if count < 1:
        raise ValueError("Candle count must be at least one")
    seconds = _interval_seconds(interval)
    current = now.astimezone(UTC)
    epoch = int(current.timestamp())
    boundary_epoch = epoch - (epoch % seconds)
    boundary = datetime.fromtimestamp(boundary_epoch, tz=UTC)
    newest_closed_open = boundary - timedelta(seconds=seconds)
    start_open = newest_closed_open - (count - 1) * timedelta(seconds=seconds)
    return start_open, newest_closed_open


class MarketIntelligenceInputBuilder:
    """Build the verified multi-timeframe bundle for one analysis request."""

    def __init__(
        self,
        *,
        historical: BinanceHistoricalCandleService,
        provenance_repository: MarketDataProvenanceRepository | None,
        require_provenance: bool,
        candles_per_timeframe: int = CANDLES_PER_TIMEFRAME,
        timeframes: tuple[str, ...] = ANALYSIS_TIMEFRAMES,
    ) -> None:
        if candles_per_timeframe < 1 or candles_per_timeframe > MAX_CANDLE_LIMIT:
            raise ValueError("candles_per_timeframe must be between 1 and 1000")
        unsupported = [tf for tf in timeframes if tf not in INTERVALS]
        if unsupported:
            raise ValueError(f"Unsupported analysis timeframes: {unsupported}")
        self._historical = historical
        self._provenance = provenance_repository
        self._require_provenance = require_provenance
        self._candles_per_timeframe = candles_per_timeframe
        self._timeframes = timeframes

    async def build(
        self,
        prepared: PreparedAnalysisInput,
        *,
        request_id: UUID | None = None,
        now: datetime | None = None,
    ) -> MarketIntelligenceInput:
        """Fetch and provenance-record every required timeframe series.

        Individual timeframe failures are captured inside the bundle rather
        than raised, so the intelligence engine can report degraded coverage
        honestly. The current price itself is mandatory and fail-closed.
        """
        if prepared.current_price is None or prepared.market_snapshot_id is None:
            raise MarketIntelligenceInputUnavailable(
                "Verified current price and provenance are required for analysis"
            )
        price = prepared.current_price
        symbol = price.symbol

        async def fetch_series(interval: str) -> TimeframeSeriesInput | None:
            start, end = closed_window(
                interval,
                count=self._candles_per_timeframe,
                now=now or datetime.now(UTC),
            )
            try:
                series = await self._historical.fetch(
                    symbol,
                    interval,  # type: ignore[arg-type]
                    start_time=start,
                    end_time=end,
                )
            except (MarketDataUnavailable, ValueError):
                return None
            if self._provenance is not None:
                try:
                    snapshot_id = await asyncio.to_thread(
                        self._provenance.record_historical_series,
                        series,
                        request_id=request_id,
                    )
                except Exception as exc:
                    raise MarketIntelligenceInputUnavailable(
                        "Historical candle series could not be persisted for audit."
                    ) from exc
                series = series.model_copy(update={"snapshot_id": snapshot_id})
            elif self._require_provenance:
                raise MarketIntelligenceInputUnavailable(
                    "Persistent market-data provenance is not configured; analysis is blocked."
                )
            return TimeframeSeriesInput(
                interval=interval,
                series=series,
                snapshot_id=series.snapshot_id,
            )

        fetch_started = perf_counter()
        results = await asyncio.gather(*(fetch_series(tf) for tf in self._timeframes))
        historical_fetch_ms = (perf_counter() - fetch_started) * 1000
        timeframes = {
            interval: entry
            for interval, entry in zip(self._timeframes, results, strict=True)
            if entry is not None
        }
        return MarketIntelligenceInput(
            price=price,
            price_snapshot_id=prepared.market_snapshot_id,
            timeframes=timeframes,
            historical_fetch_ms=round(historical_fetch_ms, 3),
        )


__all__ = [
    "CANDLES_PER_TIMEFRAME",
    "MarketIntelligenceInputBuilder",
    "MarketIntelligenceInputUnavailable",
    "closed_window",
]
