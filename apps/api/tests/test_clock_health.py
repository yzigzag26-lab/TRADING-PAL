from __future__ import annotations

import asyncio
import time

from app.core.clock_health import ClockHealthMonitor, NtpSample


def test_clock_monitor_requires_two_independent_agreeing_sources() -> None:
    async def run() -> None:
        def probe(server: str) -> NtpSample:
            offsets = {"one": 0.08, "two": 0.10, "three": 0.12}
            return NtpSample(server, offsets[server], 0.04)

        monitor = ClockHealthMonitor(
            servers=("one", "two", "three"),
            probe_interval_seconds=1,
            health_ttl_seconds=3,
            probe=probe,
        )
        snapshot = await monitor.check_once()
        assert snapshot.healthy is True
        assert snapshot.healthy_sources == 3
        assert snapshot.offset_seconds == 0.10
        assert monitor.is_healthy() is True
        await monitor.close()

    asyncio.run(run())


def test_clock_monitor_rejects_large_offset() -> None:
    async def run() -> None:
        monitor = ClockHealthMonitor(
            servers=("one", "two", "three"),
            probe_interval_seconds=1,
            health_ttl_seconds=3,
            probe=lambda server: NtpSample(server, 0.8, 0.02),
        )
        snapshot = await monitor.check_once()
        assert snapshot.healthy is False
        assert snapshot.reason == "ntp_sources_disagree_or_clock_offset_exceeded"
        assert monitor.is_healthy() is False

    asyncio.run(run())


def test_clock_monitor_rejects_disagreeing_sources() -> None:
    async def run() -> None:
        offsets = {"one": -0.4, "two": 0.0, "three": 0.4}
        monitor = ClockHealthMonitor(
            servers=("one", "two", "three"),
            probe_interval_seconds=1,
            health_ttl_seconds=3,
            probe=lambda server: NtpSample(server, offsets[server], 0.02),
        )
        snapshot = await monitor.check_once()
        assert snapshot.healthy is False
        assert snapshot.healthy_sources == 3

    asyncio.run(run())


def test_clock_monitor_fails_closed_with_fewer_than_two_sources() -> None:
    async def run() -> None:
        def probe(server: str) -> NtpSample:
            if server == "one":
                return NtpSample(server, 0.01, 0.02)
            raise TimeoutError("NTP timeout")

        monitor = ClockHealthMonitor(
            servers=("one", "two", "three"),
            probe_interval_seconds=1,
            health_ttl_seconds=3,
            probe=probe,
        )
        snapshot = await monitor.check_once()
        assert snapshot.healthy is False
        assert snapshot.healthy_sources == 1
        assert monitor.is_healthy() is False

    asyncio.run(run())


def test_clock_health_expires_when_no_successful_refresh_occurs() -> None:
    async def run() -> None:
        monitor = ClockHealthMonitor(
            servers=("one", "two"),
            probe_interval_seconds=1,
            health_ttl_seconds=2,
            probe=lambda server: NtpSample(server, 0.01, 0.02),
        )
        await monitor.check_once()
        assert monitor.is_healthy() is True
        monitor._last_success_monotonic = time.monotonic() - 3
        assert monitor.is_healthy() is False
        assert monitor.snapshot.reason == "clock_health_check_missing_or_expired"

    asyncio.run(run())
