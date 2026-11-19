"""Bounded retry policy for public Binance Spot REST requests."""

from __future__ import annotations

import asyncio
import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

from app.market_data.freshness import MarketDataUnavailable


@dataclass(frozen=True, slots=True)
class RestRetryPolicy:
    """Strict request-attempt and cumulative-wait budget."""

    max_attempts: int = 3
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 1.0
    max_total_wait_seconds: float = 2.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if (
            not math.isfinite(self.base_delay_seconds)
            or not math.isfinite(self.max_delay_seconds)
            or not math.isfinite(self.max_total_wait_seconds)
            or self.base_delay_seconds < 0
            or self.max_delay_seconds < self.base_delay_seconds
            or self.max_total_wait_seconds < 0
        ):
            raise ValueError("Retry delays must be finite, non-negative, and ordered")


DEFAULT_RETRY_POLICY = RestRetryPolicy()


def _retry_after_seconds(value: str | None) -> float | None:
    """Parse delta-seconds or an HTTP date; None means absent or invalid."""
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        seconds = float(raw)
        if math.isfinite(seconds) and seconds >= 0:
            return seconds
        return None
    except ValueError:
        pass

    try:
        retry_at = parsedate_to_datetime(raw)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        seconds = (retry_at.astimezone(UTC) - datetime.now(UTC)).total_seconds()
    except (TypeError, ValueError, OverflowError):
        return None
    return max(0.0, seconds) if math.isfinite(seconds) else None


def _backoff_seconds(attempt: int, policy: RestRetryPolicy) -> float:
    """Exponential backoff with bounded 50–100% jitter."""
    ceiling = min(
        policy.max_delay_seconds,
        policy.base_delay_seconds * (2 ** (attempt - 1)),
    )
    return random.uniform(ceiling / 2, ceiling)


async def get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, str | int],
    policy: RestRetryPolicy = DEFAULT_RETRY_POLICY,
) -> httpx.Response:
    """GET with bounded retries; never retries Binance's HTTP 418 ban response.

    HTTP 429 honours a valid Retry-After value exactly. If that delay cannot fit
    inside the cumulative wait budget, the request fails closed rather than
    retrying early. Missing/invalid Retry-After values use bounded jittered
    backoff. HTTP 408, 5xx, and transport failures are retryable.
    """
    waited = 0.0
    for attempt in range(1, policy.max_attempts + 1):
        try:
            response = await client.get(url, params=params)
        except httpx.TransportError as exc:
            if attempt >= policy.max_attempts:
                raise MarketDataUnavailable(
                    "Binance REST transport failed after bounded retries"
                ) from exc
            delay = _backoff_seconds(attempt, policy)
            reason = "transport failure"
        else:
            status = response.status_code
            if status == 418:
                retry_after = response.headers.get("Retry-After")
                raise MarketDataUnavailable(
                    "Binance REST returned HTTP 418 (IP ban); automatic retries are disabled; "
                    f"Retry-After={retry_after or 'not-provided'}"
                )
            if status == 429:
                if attempt >= policy.max_attempts:
                    raise MarketDataUnavailable(
                        "Binance REST HTTP 429 rate limit persisted after bounded retries"
                    )
                server_delay = _retry_after_seconds(response.headers.get("Retry-After"))
                delay = (
                    server_delay
                    if server_delay is not None
                    else _backoff_seconds(attempt, policy)
                )
                reason = "HTTP 429 rate limit"
            elif status == 408 or 500 <= status <= 599:
                if attempt >= policy.max_attempts:
                    raise MarketDataUnavailable(
                        f"Binance REST HTTP {status} persisted after bounded retries"
                    )
                delay = _backoff_seconds(attempt, policy)
                reason = f"HTTP {status} transient response"
            else:
                return response

        remaining = policy.max_total_wait_seconds - waited
        if delay > remaining:
            raise MarketDataUnavailable(
                f"Binance REST {reason}; required retry delay exceeds the bounded wait budget"
            )
        await asyncio.sleep(delay)
        waited += delay

    raise MarketDataUnavailable("Binance REST retry budget exhausted")
