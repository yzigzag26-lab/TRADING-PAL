# Trading Pal

Trading Pal is the repository name for **Baymax**, a private, single-owner,
mobile-first cryptocurrency trading-intelligence assistant.

Version 1 is analysis-oriented. It is intended to interpret charts, verify
observations against exchange data, calculate deterministic indicators,
synthesize evidence, and produce conditional scenarios with uncertainty and
invalidation. It does not currently execute trades.

## Repository layout

- `apps/web` — Next.js + TypeScript frontend.
- `apps/api` — Python 3.12 + FastAPI backend.
- `docs` — canonical architecture, implementation and operations docs.
- `apps/api/docs` — synchronized documentation source used by the Render
  service build for the private owner-only `/guide/` site.

## Current implementation status

- The frontend foundation is present with honest disconnected/empty states.
- The backend has a private single-owner password/session flow, a public
  liveness endpoint, CORS allow-list, request IDs, structured logs and
  standardized errors.
- Gate 1 database foundation and Gate 2 application/risk configuration
  migrations are present in the repository; consult their gate documents for
  verification and remaining hardening evidence.
- **Gate 3 Binance Spot market-data ingestion is not implemented yet.** Its
  owner-approved freshness and reliability acceptance contract is documented
  in [Gate 3 — Market Data](docs/development/GATE_3_MARKET_DATA.md).
- AI analysis, chart processing, evaluation, evidence-based learning and
  curated memory remain later gates.
- No sample prices, balances, signals, analyses or history records are
  fabricated.

## Development

- Frontend: [apps/web/README.md](apps/web/README.md)
- Backend: [apps/api/README.md](apps/api/README.md)
- Phase 1 foundation handoff: [docs/IMPLEMENTATION_HANDOFF.md](docs/IMPLEMENTATION_HANDOFF.md)
- Engineering documentation index: [docs/index.md](docs/index.md)

## Security

Never commit credentials. Never expose database passwords, session-signing
secrets, service-role credentials or private provider keys to the browser or
Git history. Gate 3 uses Binance public market data and requires no Binance
API key or secret.
