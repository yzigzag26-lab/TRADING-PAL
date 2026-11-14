# Trading Pal

Trading Pal is a private, mobile-first cryptocurrency trading intelligence workspace. Version 1 is focused on chart interpretation, market-data verification, evidence synthesis and risk-aware conditional scenarios. It does not execute trades.

## Repository layout

- `apps/web` — Next.js + TypeScript frontend, deployed independently to Vercel.
- `apps/api` — planned Python + FastAPI backend, deployed independently to Render.
- `docs` — architecture and implementation documentation.

## Current implementation status

The first frontend experience is being developed on `feat/version-1-frontend`. It includes a responsive workspace shell and honest disconnected/empty states. Authentication, persistent preferences, live market data, chart-analysis processing and risk calculations are not connected yet. No sample prices, balances, signals, analyses or history records are fabricated.

## Frontend development

See [apps/web/README.md](apps/web/README.md). Vercel should use `apps/web` as its project Root Directory.

## Architecture and scope

Read [the Phase 1 implementation handoff](docs/IMPLEMENTATION_HANDOFF.md) before changing architecture, backend scope, security boundaries or deployment configuration.

## Security

Never commit credentials. Never expose Supabase service-role credentials, database passwords, JWT signing secrets or private provider API keys to the browser or Git history.