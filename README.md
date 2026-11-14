# Trading Pal

Trading Pal is a private, mobile-first cryptocurrency trading intelligence workspace. Version 1 is focused on chart interpretation, market-data verification, evidence synthesis and risk-aware conditional scenarios. It does not execute trades.

## Repository layout

- `apps/web` — Next.js + TypeScript frontend, deployed independently to Vercel.
- `apps/api` — Python 3.12 + FastAPI backend, prepared for Render.
- `docs` — architecture and implementation documentation.

## Current implementation status

The frontend foundation is present with honest disconnected/empty states. The backend now runs a minimal FastAPI application with a public liveness endpoint, CORS allow-list, request IDs, structured logs, and standardized errors. Supabase authentication, persistent preferences, live market data, chart-analysis processing and risk calculations are not connected yet. No sample prices, balances, signals, analyses or history records are fabricated.

## Development

- Frontend: [apps/web/README.md](apps/web/README.md)
- Backend: [apps/api/README.md](apps/api/README.md)
- Architecture and scope: [Phase 1 implementation handoff](docs/IMPLEMENTATION_HANDOFF.md)

## Security

Never commit credentials. Never expose Supabase service-role credentials, database passwords, JWT signing secrets or private provider API keys to the browser or Git history.
