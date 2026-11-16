"""Fail-closed monitor for the host clock using independent NTP sources.

The monitor observes clock health; it never changes the operating-system clock.
A failed, stale, or disagreeing probe keeps current-market analysis blocked.
"""

from __future__ import annotations

import asyncio
import socket
import struct
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

NTP_EPOCH_OFFSET = 2_208_988_800
NTP_PACKET_SIZE = 48
DEFAULT_NTP_SERVERS = ("time.cloudflare.com", "time.google.com", "pool.ntp.org")
MAX_CLOCK_OFFSET_SECONDS = 0.5
MAX_NTP_ROUND_TRIP_SECONDS = 1.0
MIN_HEALTHY_SOURCES = 2
PROBE_INTERVAL_SECONDS = 30.0
HEALTH_TTL_SECONDS = 90.0
PROBE_TIMEOUT_SECONDS = 1.0


@dataclass(frozen=True, slots=True)
class NtpSample:
    """One validated NTP response and its estimated local clock offset."""

    server: str
    offset_seconds: float
    round_trip_seconds: float


@dataclass(frozen=True, slots=True)
class ClockHealthSnapshot:
    """Immutable view of the most recent clock consensus decision."""

    healthy: bool
    checked_at: datetime | None
    offset_seconds: float | None
    healthy_sources: int
    reason: str


def _ntp_timestamp(epoch_seconds: float) -> bytes:
    seconds = int(epoch_seconds) + NTP_EPOCH_OFFSET
    fraction = int((epoch_seconds % 1) * (2**32))
    return struct.pack("!II", seconds, fraction)


def _decode_ntp_timestamp(packet: bytes, offset: int) -> float:
    seconds, fraction = struct.unpack("!II", packet[offset : offset + 8])
    return seconds - NTP_EPOCH_OFFSET + fraction / 2**32


def query_ntp_server(
    server: str,
    *,
    timeout_seconds: float = PROBE_TIMEOUT_SECONDS,
    socket_factory: Callable[..., socket.socket] = socket.socket,
) -> NtpSample:
    """Query one NTP server and calculate offset using the four-timestamp method."""
    packet = bytearray(NTP_PACKET_SIZE)
    packet[0] = 0x23  # LI=0, VN=4, client mode.
    t1 = time.time()
    request_timestamp = _ntp_timestamp(t1)
    packet[40:48] = request_timestamp
    started = time.monotonic()

    with socket_factory(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.settimeout(timeout_seconds)
        client.sendto(packet, (server, 123))
        response, _ = client.recvfrom(512)

    t4 = time.time()
    round_trip = time.monotonic() - started
    if len(response) < NTP_PACKET_SIZE:
        raise ValueError("NTP response is shorter than 48 bytes")

    leap_indicator = response[0] >> 6
    mode = response[0] & 0x07
    stratum = response[1]
    if leap_indicator == 3 or mode != 4 or not 1 <= stratum <= 15:
        raise ValueError("NTP server response is not synchronized")
    if response[24:32] != request_timestamp:
        raise ValueError("NTP originate timestamp does not match the request")

    t2 = _decode_ntp_timestamp(response, 32)
    t3 = _decode_ntp_timestamp(response, 40)
    if t2 <= 0 or t3 < t2:
        raise ValueError("NTP server timestamps are invalid")

    offset = ((t2 - t1) + (t3 - t4)) / 2
    corrected_round_trip = round_trip - (t3 - t2)
    if corrected_round_trip < 0 or corrected_round_trip > MAX_NTP_ROUND_TRIP_SECONDS:
        raise ValueError("NTP round-trip delay is outside the accepted range")
    return NtpSample(server, offset, corrected_round_trip)


class ClockHealthMonitor:
    """Periodically verify host clock offset against independent NTP sources."""

    def __init__(
        self,
        *,
        servers: tuple[str, ...] = DEFAULT_NTP_SERVERS,
        probe_interval_seconds: float = PROBE_INTERVAL_SECONDS,
        health_ttl_seconds: float = HEALTH_TTL_SECONDS,
        probe: Callable[[str], NtpSample] = query_ntp_server,
    ) -> None:
        if len(set(servers)) < MIN_HEALTHY_SOURCES:
            raise ValueError("At least two distinct NTP sources are required")
        if probe_interval_seconds <= 0 or health_ttl_seconds <= probe_interval_seconds:
            raise ValueError("Clock monitor intervals are invalid")
        self._servers = servers
        self._probe_interval = probe_interval_seconds
        self._health_ttl = health_ttl_seconds
        self._probe = probe
        self._snapshot = ClockHealthSnapshot(False, None, None, 0, "not_checked")
        self._last_success_monotonic: float | None = None
        self._task: asyncio.Task[None] | None = None
        self._closed = False

    @property
    def snapshot(self) -> ClockHealthSnapshot:
        """Return health only while the last successful consensus is within its TTL."""
        if (
            self._snapshot.healthy
            and self._last_success_monotonic is not None
            and time.monotonic() - self._last_success_monotonic <= self._health_ttl
        ):
            return self._snapshot
        return ClockHealthSnapshot(
            False,
            self._snapshot.checked_at,
            self._snapshot.offset_seconds,
            self._snapshot.healthy_sources,
            "clock_health_check_missing_or_expired",
        )

    def is_healthy(self) -> bool:
        """Synchronous provider suitable for the request orchestrator."""
        return self.snapshot.healthy

    async def start(self) -> None:
        """Perform an initial probe and then maintain health in the background."""
        if self._task is not None:
            return
        self._closed = False
        await self.check_once()
        self._task = asyncio.create_task(self._run(), name="baymax-clock-health")

    async def close(self) -> None:
        """Stop background checks and invalidate the health assertion."""
        self._closed = True
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        self._snapshot = ClockHealthSnapshot(
            False,
            self._snapshot.checked_at,
            self._snapshot.offset_seconds,
            self._snapshot.healthy_sources,
            "monitor_stopped",
        )
        self._last_success_monotonic = None

    async def check_once(self) -> ClockHealthSnapshot:
        """Probe all configured sources and require independent agreement."""
        results = await asyncio.gather(
            *(asyncio.to_thread(self._probe, server) for server in self._servers),
            return_exceptions=True,
        )
        samples = [
            result
            for result in results
            if isinstance(result, NtpSample)
            and result.round_trip_seconds <= MAX_NTP_ROUND_TRIP_SECONDS
        ]
        checked_at = datetime.now(UTC)
        if len(samples) < MIN_HEALTHY_SOURCES:
            self._snapshot = ClockHealthSnapshot(
                False, checked_at, None, len(samples), "insufficient_ntp_sources"
            )
            self._last_success_monotonic = None
            return self._snapshot

        offsets = sorted(sample.offset_seconds for sample in samples)
        median_offset = (
            offsets[len(offsets) // 2]
            if len(offsets) % 2
            else (offsets[len(offsets) // 2 - 1] + offsets[len(offsets) // 2]) / 2
        )
        spread = max(offsets) - min(offsets)
        healthy = (
            abs(median_offset) <= MAX_CLOCK_OFFSET_SECONDS and spread <= MAX_CLOCK_OFFSET_SECONDS
        )
        reason = "healthy" if healthy else "ntp_sources_disagree_or_clock_offset_exceeded"
        self._snapshot = ClockHealthSnapshot(
            healthy, checked_at, median_offset, len(samples), reason
        )
        self._last_success_monotonic = time.monotonic() if healthy else None
        return self._snapshot

    async def _run(self) -> None:
        while not self._closed:
            await asyncio.sleep(self._probe_interval)
            if not self._closed:
                await self.check_once()
