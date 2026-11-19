"""Deterministic tests for bounded public Binance REST retry behaviour."""

import asyncio

import httpx
import pytest

from app.market_data.freshness import MarketDataUnavailable
from app.market_data.rest_retry import RestRetryPolicy, get_with_retry


def test_429_honours_retry_after_before_retrying(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        delays: list[float] = []
        calls = 0

        async def sleep(delay: float) -> None:
            delays.append(delay)

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(429, headers={"Retry-After": "1"})
            return httpx.Response(200, json={"ok": True})

        monkeypatch.setattr("app.market_data.rest_retry.asyncio.sleep", sleep)
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        response = await get_with_retry(
            client,
            "https://test.invalid/api",
            params={},
            policy=RestRetryPolicy(max_total_wait_seconds=1.5),
        )
        assert response.status_code == 200
        assert calls == 2
        assert delays == [1.0]
        await client.aclose()

    asyncio.run(run())


def test_429_delay_beyond_budget_fails_without_early_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        calls = 0

        async def sleep(_: float) -> None:
            raise AssertionError("A delay beyond the budget must not sleep or retry")

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(429, headers={"Retry-After": "10"})

        monkeypatch.setattr("app.market_data.rest_retry.asyncio.sleep", sleep)
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with pytest.raises(MarketDataUnavailable, match="exceeds the bounded wait budget"):
            await get_with_retry(
                client,
                "https://test.invalid/api",
                params={},
                policy=RestRetryPolicy(max_total_wait_seconds=2),
            )
        assert calls == 1
        await client.aclose()

    asyncio.run(run())


def test_429_without_retry_after_uses_bounded_jittered_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        delays: list[float] = []
        calls = 0

        async def sleep(delay: float) -> None:
            delays.append(delay)

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(429) if calls == 1 else httpx.Response(200)

        monkeypatch.setattr("app.market_data.rest_retry.asyncio.sleep", sleep)
        monkeypatch.setattr("app.market_data.rest_retry.random.uniform", lambda low, high: high)
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        response = await get_with_retry(
            client,
            "https://test.invalid/api",
            params={},
        )
        assert response.status_code == 200
        assert calls == 2
        assert delays == [0.25]
        await client.aclose()

    asyncio.run(run())


def test_418_ban_is_never_retried_even_with_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        calls = 0

        async def sleep(_: float) -> None:
            raise AssertionError("HTTP 418 must never be retried")

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(418, headers={"Retry-After": "1"})

        monkeypatch.setattr("app.market_data.rest_retry.asyncio.sleep", sleep)
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with pytest.raises(MarketDataUnavailable, match="HTTP 418.*automatic retries are disabled"):
            await get_with_retry(client, "https://test.invalid/api", params={})
        assert calls == 1
        await client.aclose()

    asyncio.run(run())


def test_transient_server_failure_retries_with_exponential_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        delays: list[float] = []
        calls = 0

        async def sleep(delay: float) -> None:
            delays.append(delay)

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(503) if calls < 3 else httpx.Response(200)

        monkeypatch.setattr("app.market_data.rest_retry.asyncio.sleep", sleep)
        monkeypatch.setattr("app.market_data.rest_retry.random.uniform", lambda low, high: high)
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        response = await get_with_retry(
            client,
            "https://test.invalid/api",
            params={},
        )
        assert response.status_code == 200
        assert calls == 3
        assert delays == [0.25, 0.5]
        await client.aclose()

    asyncio.run(run())


def test_transport_failure_retries_and_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        calls = 0

        async def sleep(_: float) -> None:
            return None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise httpx.ConnectError("temporary network failure", request=request)
            return httpx.Response(200)

        monkeypatch.setattr("app.market_data.rest_retry.asyncio.sleep", sleep)
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        response = await get_with_retry(
            client,
            "https://test.invalid/api",
            params={},
        )
        assert response.status_code == 200
        assert calls == 2
        await client.aclose()

    asyncio.run(run())


def test_retry_exhaustion_is_bounded_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        calls = 0

        async def sleep(_: float) -> None:
            return None

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(503)

        monkeypatch.setattr("app.market_data.rest_retry.asyncio.sleep", sleep)
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with pytest.raises(MarketDataUnavailable, match="HTTP 503.*bounded retries"):
            await get_with_retry(
                client,
                "https://test.invalid/api",
                params={},
                policy=RestRetryPolicy(max_attempts=2),
            )
        assert calls == 2
        await client.aclose()

    asyncio.run(run())


def test_permanent_client_error_is_not_retried() -> None:
    async def run() -> None:
        calls = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(400)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        response = await get_with_retry(client, "https://test.invalid/api", params={})
        assert response.status_code == 400
        assert calls == 1
        await client.aclose()

    asyncio.run(run())


def test_invalid_retry_policy_is_rejected() -> None:
    with pytest.raises(ValueError, match="Retry delays"):
        RestRetryPolicy(max_total_wait_seconds=-1)


def test_overall_deadline_cancels_slow_request_and_fails_closed() -> None:
    async def run() -> None:
        calls = 0

        async def handler(_: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            await asyncio.Event().wait()
            return httpx.Response(200)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with pytest.raises(MarketDataUnavailable, match="overall retry deadline"):
            await get_with_retry(
                client,
                "https://test.invalid/api",
                params={},
                policy=RestRetryPolicy(max_elapsed_seconds=0.01),
            )
        assert calls == 1
        await client.aclose()

    asyncio.run(run())
