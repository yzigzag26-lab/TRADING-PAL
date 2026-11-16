# Environment variables

This inventory documents variable names only. Use placeholders in templates
and configure real values only in local environment files or approved hosting
secret stores. Never commit a real `.env` file.

## Frontend — `apps/web`

No frontend environment variables are required by the current implementation.
The browser calls same-origin `/api/*` routes, and Next.js rewrites them to the
backend. The backend origin is currently configured in `apps/web/next.config.ts`.
Do not add unused `NEXT_PUBLIC_SUPABASE_*` or `NEXT_PUBLIC_API_BASE_URL`
variables. Never put a secret in a browser-exposed variable.

## Backend — `apps/api` and Render service

| Variable | Required now | Purpose |
|---|---|---|
| `APP_ENV` | Yes | `development`, `test`, or `production` |
| `LOG_LEVEL` | No | Python logging level; defaults to `INFO` |
| `CORS_ALLOWED_ORIGINS` | Yes in production | Comma-separated exact browser origins; no wildcard |
| `BAYMAX_PASSWORD_HASH` | Required to enable login | Argon2id hash generated locally with `python scripts/create_password_hash.py`; never the plaintext password |
| `BAYMAX_SESSION_SECRET` | Required to enable login | Random secret used to sign the owner session cookie |
| `DATABASE_URL` | Required in deployed backend | Supabase PostgreSQL connection authenticated as `baymax_runtime` |
| `MIGRATION_DATABASE_URL` | Operator/CI only | Privileged migration connection; never a Render or Vercel runtime variable |

## Later-stage variables — not used by the current API

| Variable | Purpose |
|---|---|
| `BINANCE_REST_BASE_URL` | Optional non-secret base URL; Gate 3 default is `https://data-api.binance.vision` |
| `BINANCE_WS_BASE_URL` | Optional non-secret base URL; Gate 3 default is `wss://data-stream.binance.vision` |
| `GROQ_API_KEY` | Server-side Groq credential for a later AI phase |
| `GROQ_VISION_MODEL` | Vision model identifier |
| `GROQ_REASONING_MODEL` | Reasoning model identifier |
| `SUPABASE_CHARTS_BUCKET` | Private chart-storage bucket name |

The Binance base-URL names above are proposed configuration names for the
future Gate 3 implementation; they are not consumed by the current API.
**No Binance API key, secret, signature, or receive-window variable is
required for public Spot market data.**

## Secret-handling rules

- Never expose database passwords, session-signing secrets, service-role
  credentials, or future AI-provider credentials in browser variables.
- Keep privileged migration credentials out of Render runtime and Vercel.
- Never paste credentials into source code, issues, pull requests, chat, or CI
  logs.
- Gate 3 uses public Binance Spot market data only and requires no Binance
  credentials. Do not add private account or trading access.
- Do not activate paid services without owner approval.
