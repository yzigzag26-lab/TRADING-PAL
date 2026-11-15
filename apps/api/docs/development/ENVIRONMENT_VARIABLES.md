# Environment variables

This inventory documents variable names only. Use placeholders in templates
and configure real values only in local environment files or approved hosting
secret stores. Never commit a real `.env` file.

## Frontend — `apps/web/.env.local`

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Public Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Browser-safe Supabase publishable key |
| `NEXT_PUBLIC_API_BASE_URL` | Public FastAPI base URL |

## Backend — `apps/api` and Render service

| Variable | Required now | Purpose |
|---|---|---|
| `APP_ENV` | Yes | `development`, `test`, or `production` |
| `LOG_LEVEL` | No | Python logging level; defaults to `INFO` |
| `CORS_ALLOWED_ORIGINS` | Yes in production | Comma-separated exact browser origins; no wildcard |
| `BAYMAX_PASSWORD_HASH` | Required to enable login | Argon2id hash generated locally with `python scripts/create_password_hash.py`; never the plaintext password |
| `BAYMAX_SESSION_SECRET` | Required to enable login | Random secret used to sign the owner session cookie; generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"` |

The production backend requires `DATABASE_URL` for its dedicated runtime database
login. The migration credential is intentionally not a Render variable.

## Later-stage variables — not used by the current API

| Variable | Purpose |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_PUBLISHABLE_KEY` | Supabase publishable key; never a service-role key |
| `SUPABASE_JWKS_URL` | Supabase Auth JWKS endpoint |
| `SUPABASE_JWT_ISSUER` | Expected JWT issuer |
| `DATABASE_URL` | Set on Render when the runtime database is provisioned; authenticates as `baymax_runtime` |
| `MIGRATION_DATABASE_URL` | Private operator environment only; privileged PostgreSQL connection authenticated as `baymax_migration`; never set on Render or Vercel |
| `BINANCE_API_KEY` | Dedicated read-only key for the later market-data phase |
| `BINANCE_API_SECRET` | Secret paired with that read-only key |
| `BINANCE_REST_BASE_URL` | Approved Binance REST base URL |
| `BINANCE_RECV_WINDOW_MS` | Binance request receive window |
| `GROQ_API_KEY` | Server-side Groq credential for a later AI phase |
| `GROQ_VISION_MODEL` | Vision model identifier |
| `GROQ_REASONING_MODEL` | Reasoning model identifier |
| `SUPABASE_CHARTS_BUCKET` | Private chart-storage bucket name |

## Secret-handling rules

- Never expose service-role keys, database passwords, JWT signing secrets,
  Binance credentials, or Groq credentials in browser variables.
- Never paste credentials into source code, issues, pull requests, chat, or CI
  logs.
- Binance access remains out of scope until the market-data phase is approved.
  Use read-only permissions only; never enable trading, transfers, withdrawals,
  margin, or futures permissions.
- Do not activate paid services without owner approval.
