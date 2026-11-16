# Baymax Web

Next.js frontend for Baymax, the private single-owner trading-intelligence
assistant. The app is designed to deploy from this monorepo with **Vercel Root
Directory = `apps/web`**.

## Local development

Requirements: Node.js 20.9+ and npm.

```bash
cd apps/web
npm install
npm run dev
```

Open http://localhost:3000.

## Authentication and backend integration

The password screen is connected to the FastAPI single-owner session flow:
- `POST /api/v1/auth/login` verifies the owner password and sets the secure
  session cookie.
- `GET /api/v1/auth/session` restores the session state.
- `POST /api/v1/auth/logout` clears the browser cookie.

The frontend calls the same-origin `/api/*` path. Next.js rewrites forward
those requests to the Render backend. The browser does not connect directly to
PostgreSQL or use Supabase Auth. Do not add database credentials, session
secrets, or provider API keys to frontend variables.

Authentication being connected does **not** mean market data or AI analysis is
connected. Dashboard metrics, market prices, watchlists, chart analysis,
risk results, and history remain honest empty/disconnected states until their
backend gates are implemented. No market data or analysis is fabricated.

## Environment

No frontend environment variables are required by the current implementation.
The backend destination is configured in `next.config.ts`; the browser uses
same-origin API paths and the owner session cookie. Do not add unused
`NEXT_PUBLIC_SUPABASE_*` or `NEXT_PUBLIC_API_BASE_URL` settings.

## Quality checks

```bash
npm run typecheck
npm run lint
npm run build
```

## Vercel

Import the repository and set the project Root Directory to `apps/web`. Use
the build command from this package's `package.json`. Keep all backend
credentials and private configuration in the approved backend secret store.
