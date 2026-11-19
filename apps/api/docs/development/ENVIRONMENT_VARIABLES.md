# Environment variables

This inventory documents variables consumed by the current implementation and
clearly labels proposed future configuration. Use placeholders in templates
and configure real values only in local environment files or approved hosting
secret stores. Never commit a real `.env` file.

## Frontend — `apps/web`

No frontend environment variables are required by the current implementation.
The browser calls same-origin `/api/*` routes, and Next.js rewrites them to the
backend. The backend origin is currently configured in
`apps/web/next.config.ts`. Do not add unused `NEXT_PUBLIC_SUPABASE_*` or
`NEXT_PUBLIC_API_BASE_URL` variables. Never put a secret in a
browser-exposed variable.

## Backend — `apps/api` and Render service

| Variable | Required now | Purpose |
|---|---|---|
| `APP_ENV` | Yes | `development`, `test`, or `production` |
| `LOG_LEVEL` | No | Python logging level; defaults to `INFO` |
| `CORS_ALLOWED_ORIGINS` | Yes in production | Comma-separated exact browser origins; no wildcard |
| `BAYMAX_PASSWORD_HASH` | Required to enable login | Argon2id hash generated locally with `python scripts/create_password_hash.py`; never the plaintext password |
| `BAYMAX_SESSION_SECRET` | Required to enable login | Random secret used to sign the owner session cookie |
| `DATABASE_URL` | Required in deployed backend | Supabase PostgreSQL connection authenticated as `baymax_runtime` |
| `GROQ_API_KEY` | Required for AI responses | Private Groq API credential; configure on Render only |
| `GROQ_MODEL` | No | Groq model identifier; defaults to `openai/gpt-oss-20b` |
| `MIGRATION_DATABASE_URL` | Operator/CI only | Privileged migration connection; never a Render or Vercel runtime variable |

The backend settings currently read `GROQ_API_KEY` and `GROQ_MODEL`.
Separate `GROQ_VISION_MODEL` and `GROQ_REASONING_MODEL` settings are not
implemented and must not be configured as if the application consumes them.

## Proposed future configuration — not consumed by the current API

| Variable | Purpose |
|---|---|
| `BINANCE_REST_BASE_URL` | Proposed non-secret REST base URL; current Gate 3 code uses its configured public Binance Spot market-data host |
| `BINANCE_WS_BASE_URL` | Proposed non-secret WebSocket base URL; current Gate 3 code uses its configured public Binance Spot market-data host |
| `SUPABASE_CHARTS_BUCKET` | Proposed private chart-storage bucket name; chart storage is not implemented |

These names are inventory/planning entries only. They are not current runtime
settings. Production clock health is checked with public NTP sources over
UDP/123; it has no secret or environment-variable override.

**No Binance API key, secret, signature, or receive-window variable is
required for public Spot market data.**

## Secret-handling rules

- Never expose database passwords, session-signing secrets, service-role
  credentials, or AI-provider credentials in browser variables.
- Keep privileged migration credentials out of Render runtime and Vercel.
- Never paste credentials into source code, issues, pull requests, chat, or CI
  logs.
- Gate 3 uses public Binance Spot market data only and requires no Binance
  credentials. Do not add private account or trading access.
- Do not activate paid services without owner approval.
