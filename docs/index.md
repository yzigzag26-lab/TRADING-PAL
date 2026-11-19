# Baymax engineering documentation

Baymax is a private, single-owner, mobile-first cryptocurrency trading-intelligence assistant. Version 1 is analysis-oriented and does not currently execute trades.

## Start here

- [Archived Phase 1 planning baseline — historical reference only](IMPLEMENTATION_HANDOFF.md)
- [Local development](development/LOCAL_DEVELOPMENT.md)
- [Testing and Gate 3 acceptance](development/TESTING.md)
- [Environment variables](development/ENVIRONMENT_VARIABLES.md)
- [Gate 2 configuration](development/GATE_2_CONFIGURATION.md)
- [Gate 3 — Binance Spot market-data freshness and reliability](development/GATE_3_MARKET_DATA.md)
- [Security](operations/SECURITY.md)
- [Deployment operations](operations/DEPLOYMENT.md)
- [Binance public market-data setup](operations/BINANCE_API_SETUP.md)

## Current implementation status

The repository contains a runnable FastAPI backend with private single-owner
password/session authentication, a public liveness endpoint, strict CORS,
request correlation, structured logs, standardized errors, the Gate 1/2
database foundation, and the Gate 3 Binance Spot market-data pipeline. The
private Zensical site is served under `/guide/` using the existing owner
session. Supabase PostgreSQL is connected to the production API for append-only
market-data provenance.

**Gate 3 remains incomplete.** Production NTP/REST smoke checks, the durable
BTCUSDT snapshot commit/readback, and the G3-05 forced WebSocket rotation
diagnostic are recorded. G3-06 trade-sequence integrity and G3-07 candle
integrity have merged deterministic CI evidence. G3-08 is not applicable
because no local depth book exists in the current scope. G3-09 rate-limit and
transient-error handling is the next implementation criterion. See the
[Gate 3 acceptance contract](development/GATE_3_MARKET_DATA.md).
