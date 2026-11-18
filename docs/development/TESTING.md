# Testing and quality checks

The backend foundation must be testable from a clean checkout and must not
require production credentials or a live Supabase project.

## Backend

From apps/api with Python 3.12 and the development extra installed:

    ruff format --check app tests
    ruff check app tests
    mypy app tests
    pytest

The backend test suite now includes deterministic market-data coverage in
addition to the API foundation: price freshness, REST recovery, cache
revalidation, WebSocket lifecycle and trade-ID handling, clock-health failure
modes, historical candle integrity, and provenance persistence. These tests
are not a substitute for the production evidence required by the Gate 3
acceptance contract. Gate 3 has no trading or order-execution capability.

## Gate 3 — mandatory acceptance testing

The binding requirements are documented in
[Gate 3 — Binance Spot market data freshness and reliability](GATE_3_MARKET_DATA.md).
Gate 3 must not be accepted merely because a Binance connection succeeds.

At minimum, implementation tests must prove:

- Price-event age at the 3,000 ms boundary: accept at or below the limit and
  reject above it.
- A market-dependent current query refreshes or rejects an expired cache.
- Missing/untrusted timestamps, clock-health failures and unhealthy sources
  fail closed.
- WebSocket disconnect, ping/pong, reconnect, resubscription and recovery.
- Duplicate/out-of-order events and applicable sequence-gap handling.
- Candle OHLC integrity, open/closed state and missing-interval recovery.
- Order-book snapshot/update-ID synchronization if depth books are included.
- HTTP 429/418, Retry-After, bounded retry and backoff behaviour.
- Provenance/audit records for data consumed by analysis.
- Trading-decision rejection when required data is stale, incomplete,
  contradictory or unverified.

Use deterministic unit tests and simulated transport failures for repeatable
coverage. Add a live Binance smoke test for real payload compatibility, but do
not make external network availability the only way to run the unit suite.
Record exact test commands, results, skipped checks and evidence for each
acceptance criterion.

## Documentation

From the repository root:

    python -m pip install -r requirements-docs.txt
    zensical build --strict

Strict mode must fail on broken internal links and validation issues. Fix the
source rather than suppressing a valid warning.

## Frontend

From apps/web:

    npm install
    npm run lint
    npm run typecheck
    npm run build

A check that was not run must be reported as **not run**, with its reason.
