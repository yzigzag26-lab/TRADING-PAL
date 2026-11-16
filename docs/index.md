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
request correlation, structured logs, standardized errors, and the Gate 1/2
database/configuration foundation. The private Zensical site is served under
`/guide/` using the existing owner session.

**Gate 3 is documented but not implemented.** Its acceptance contract requires
fresh, validated Binance Spot market data, a maximum 3-second price-event age,
and strict refusal of trading decisions when required data is stale or
unverified. AI analysis, evaluation, learning and curated memory remain later
gates.
