"""Final fail-closed validation immediately before AI response generation."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from app.market_data.candles import HistoricalCandleSeries, expected_open_times
from app.orchestration.requests import AnalysisInputUnavailable, AnalysisRequest, PreparedAnalysisInput


def is_trading_decision_request(message: str, *, intent: str) -> bool:
    """Conservatively identify explicit buy/sell/position requests."""
    explicit_request = re.search(
        r"\b(should\s+i|would\s+you|do\s+you\s+recommend|recommend\s+me|"
        r"give\s+me\s+(?:a\s+)?(?:trading\s+)?signal|buy\s+or\s+sell|"
        r"long\s+or\s+short|where\s+should\s+i\s+(?:enter|exit)|"
        r"set\s+(?:a\s+)?stop[- ]loss|take[- ]profit)\b",
        message,
        flags=re.IGNORECASE,
    )
    if explicit_request is not None:
        return True
    if intent != "current_market":
        return False
    return re.search(
        r"\b(recommend(?:ation)?|buy|sell|hold|go\s+long|go\s+short|"
        r"entry|exit|stop[- ]loss|take[- ]profit|trading\s+signal|trade\s+signal)\b",
        message,
        flags=re.IGNORECASE,
    ) is not None

def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AnalysisInputUnavailable(f"{label} must be timezone-aware.")
    return value.astimezone(UTC)


def validate_historical_series_for_decision(
    series: HistoricalCandleSeries,
    *,
    expected_symbol: str,
    now: datetime,
) -> None:
    """Reject historical evidence unless it is complete, closed, continuous and traceable."""
    current_time = _utc(now, "Decision validation time")
    if series.symbol != expected_symbol.strip().upper():
        raise AnalysisInputUnavailable("Historical series symbol does not match the requested market.")
    if series.source != "binance_spot_rest" or series.snapshot_id is None:
        raise AnalysisInputUnavailable("Historical series has no trusted, traceable provenance.")
    if not series.complete or series.missing_open_times:
        raise AnalysisInputUnavailable("Historical series is incomplete or contains unresolved candle gaps.")
    if not series.candles:
        raise AnalysisInputUnavailable("Historical series contains no candles.")
    try:
        expected = expected_open_times(series.requested_start, series.requested_end, series.interval)
    except ValueError as exc:
        raise AnalysisInputUnavailable("Historical series range is invalid.") from exc
    actual = tuple(candle.open_time for candle in series.candles)
    if actual != tuple(expected):
        raise AnalysisInputUnavailable("Historical candle sequence is incomplete or contradictory.")
    for candle in series.candles:
        if candle.symbol != series.symbol or candle.interval != series.interval:
            raise AnalysisInputUnavailable("Historical candle identity conflicts with its series.")
        if not candle.is_closed or candle.close_time >= current_time:
            raise AnalysisInputUnavailable("Open candles cannot be used for a trading decision.")
        received_time = _utc(candle.received_time, "Candle receive timestamp")
        if received_time < candle.close_time or received_time > current_time:
            raise AnalysisInputUnavailable("Historical candle receive timestamp is contradictory.")


def validate_prepared_analysis_inputs(
    request: AnalysisRequest,
    prepared: PreparedAnalysisInput,
    *,
    now: datetime,
) -> None:
    """Revalidate all decision inputs at the final boundary before model generation."""
    current_time = _utc(now, "Decision validation time")

    if request.decision_requested:
        raise AnalysisInputUnavailable(
            "A trading recommendation is blocked: Baymax currently has no complete, closed "
            "historical candle series and validated strategy evidence for this decision."
        )

    if request.intent in {"educational", "programming"}:
        if (
            prepared.market_data_required
            or prepared.market_data_status != "not_required"
            or prepared.current_price is not None
            or prepared.market_snapshot_id is not None
        ):
            raise AnalysisInputUnavailable("Non-market response contains unexpected market evidence.")
        return

    if request.intent == "historical_market":
        raise AnalysisInputUnavailable(
            "Historical decision analysis is unavailable until complete, closed and audited "
            "historical-series inputs are connected to the analysis pipeline."
        )

    if (
        not prepared.market_data_required
        or prepared.market_data_status != "ready"
        or prepared.current_price is None
    ):
        raise AnalysisInputUnavailable("Required market evidence is missing or not ready.")
    if prepared.market_snapshot_id is None:
        raise AnalysisInputUnavailable("Market snapshot/audit provenance is missing.")

    price = prepared.current_price
    if request.symbol is None or price.symbol != request.symbol:
        raise AnalysisInputUnavailable("Market symbol does not match the classified request.")
    if price.exchange != "BINANCE" or price.market != "SPOT":
        raise AnalysisInputUnavailable("Market source identity is not an approved Binance Spot feed.")
    if price.source not in {"binance_spot_websocket", "binance_spot_rest"}:
        raise AnalysisInputUnavailable("Market source is not trusted.")
    if price.event_id is None or not price.event_id.isdecimal():
        raise AnalysisInputUnavailable("Market event sequence identity is missing or invalid.")

    market_time = _utc(price.market_event_timestamp, "Market event timestamp")
    received_time = _utc(price.received_timestamp, "Receive timestamp")
    validated_time = _utc(price.validated_timestamp, "Validation timestamp")
    if not market_time <= received_time <= validated_time <= current_time:
        raise AnalysisInputUnavailable("Market timestamps are contradictory or from the future.")
    if price.exchange_event_timestamp is not None:
        exchange_time = _utc(price.exchange_event_timestamp, "Exchange event timestamp")
        if not market_time <= exchange_time <= received_time:
            raise AnalysisInputUnavailable("Exchange and market event timestamps contradict each other.")

    age_at_validation_ms = int((validated_time - market_time).total_seconds() * 1_000)
    age_now_ms = int((current_time - market_time).total_seconds() * 1_000)
    if age_at_validation_ms != price.age_ms_at_validation:
        raise AnalysisInputUnavailable("Recorded market freshness does not match its timestamps.")
    if age_now_ms < 0 or age_now_ms > 3_000:
        raise AnalysisInputUnavailable("Market data expired before decision generation.")
