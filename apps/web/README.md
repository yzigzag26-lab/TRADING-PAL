# Trading Pal Web

Next.js frontend for Trading Pal Version 1. The app is designed to deploy from this monorepo with **Vercel Root Directory = `apps/web`**.

## Local development

Requirements: Node.js 20.9+ and npm.

```bash
cd apps/web
npm install
cp .env.example .env.local
npm run dev
```

Open http://localhost:3000.

## Quality checks

```bash
npm run typecheck
npm run lint
npm run build
```

## Environment

See `.env.example`. Only public Supabase URL/anon key and the public backend base URL belong in browser-exposed variables. Never add a service-role key, database password, JWT signing secret, or private API credential to this app.

## Current integration status

The interface deliberately shows honest disconnected and empty states. No market prices, balances, signals, analysis results, or history records are fabricated. Authentication and backend integration are not yet wired; these require the approved FastAPI and Supabase stages.

## Vercel

Import the repository and set the project Root Directory to `apps/web`. Use the build command from this package's `package.json`. Configure only the public environment variables required by the integration stage.