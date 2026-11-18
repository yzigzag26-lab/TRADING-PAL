# Baymax engineering documentation

Baymax is a private, single-owner, mobile-first cryptocurrency trading-intelligence assistant. Version 1 is analysis-oriented and does not currently execute trades.

## Start here

- [Phase 1 implementation handoff](IMPLEMENTATION_HANDOFF.md)
- [Claude work allocation](https://github.com/yzigzag26-lab/TRADING-PAL/blob/main/CLAUDE_WORKS.md)
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

**Gate 3 is implemented and undergoing acceptance testing, not complete.**
The production NTP, Binance REST/basic WebSocket smoke checks, and one durable
BTCUSDT snapshot commit with independent Supabase readback have passed. Full
WebSocket lifecycle recovery and the remaining acceptance-contract evidence
are still open. The binding requirements remain fresh, validated Binance Spot
market data, a maximum 3-second price-event age, and strict fail-closed
behaviour. AI evaluation, learning and curated memory remain later gates.
