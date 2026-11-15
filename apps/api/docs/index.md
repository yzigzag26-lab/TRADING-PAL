# Baymax engineering documentation

Baymax is a private, mobile-first cryptocurrency trading-intelligence workspace.
Version 1 is analysis-oriented and does not execute trades.

## Start here

- [Phase 1 implementation handoff](IMPLEMENTATION_HANDOFF.md)
- [Claude work allocation](https://github.com/yzigzag26-lab/TRADING-PAL/blob/main/CLAUDE_WORKS.md)
- [Local development](development/LOCAL_DEVELOPMENT.md)
- [Testing](development/TESTING.md)
- [Environment variables](development/ENVIRONMENT_VARIABLES.md)
- [Security](operations/SECURITY.md)
- [Deployment operations](operations/DEPLOYMENT.md)
- [Binance API setup for the later market-data phase](operations/BINANCE_API_SETUP.md)

## Current foundation status

The repository now contains a runnable FastAPI application with a public
liveness endpoint, versioned routing, strict CORS configuration, request
correlation, structured logs, standardized error responses, and single-owner
password authentication. The private Zensical site is served by the same API
under `/guide/` and requires the existing owner session for every page and
static asset. Database-backed application features, market data, and AI
integrations remain gated by the approved Phase 1 sequence.
