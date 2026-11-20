# Baymax API

The backend now contains the first Phase 1 application milestone: a Python 3.12
FastAPI service with a public liveness endpoint, strict CORS allow-list,
request correlation, structured JSON logs, and a consistent error envelope.

Authentication is implemented with the private single-owner session. Gate 1
provisions the private PostgreSQL schema and migration infrastructure. Gate 2
adds singleton application and risk configuration models. Gate 3 market-data requirements are documented in [the Gate 3 acceptance contract](docs/development/GATE_3_MARKET_DATA.md). Current-price ingestion, production NTP monitoring, historical OHLCV retrieval, append-only provenance, and WebSocket lifecycle recovery are implemented. Production NTP/REST/basic WebSocket smoke checks and one durable BTCUSDT snapshot commit with independent Supabase readback have passed. Gate 3 remains incomplete pending full deployed-service WebSocket lifecycle/recovery evidence and the remaining acceptance criteria. Intelligence is implemented; evaluation, learning, and persistent conversation memory remain outstanding.

## Local development

From this directory:

    python3.12 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install -e ".[dev]"
    uvicorn app.main:app --reload

On Windows PowerShell:

    py -3.12 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    python -m pip install -e ".[dev]"
    $env:APP_ENV = "development"
    $env:CORS_ALLOWED_ORIGINS = "http://localhost:3000,https://baymax-nu.vercel.app"
    uvicorn app.main:app --reload

The API listens at http://127.0.0.1:8000.

## Authentication

Baymax uses one owner password. There is no username, email, registration, or OTP flow. The backend verifies the password against an Argon2id hash supplied through `BAYMAX_PASSWORD_HASH`; the plaintext password is never stored in the repository or Render environment.

The login UI calls `POST /api/v1/auth/login`, checks `GET /api/v1/auth/session`, and signs out through `POST /api/v1/auth/logout`. A successful login sets a `__Host-baymax_session` cookie with `Secure`, `HttpOnly`, `SameSite=Lax`, and `Path=/`. The cookie is signed by `BAYMAX_SESSION_SECRET` and expires after eight hours. Rotate the session secret to invalidate all previously issued sessions. Logout clears the current browser cookie; it cannot revoke a copied stateless cookie before its expiry.

Generate the password hash locally from this directory with `python scripts/create_password_hash.py`. The script prompts twice and prints only the Argon2id hash. Set that output and a fresh random session secret in Render environment variables. Generate a session secret with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Never send either value in chat, commit them, or put them in Vercel environment variables.

The Vercel frontend proxies `/api/*` and `/guide/*` through to Render so the browser uses a same-origin cookie. Zensical is built during the Render service build into `app/static/guide`; FastAPI serves it only after validating the existing `__Host-baymax_session` cookie. The same authentication middleware protects HTML pages and every static asset. The backend-local documentation sources live in `apps/api/docs` because the Render service root is `apps/api`.

## Private engineering documentation

The private Zensical site is served at `/guide/` through the Vercel same-origin rewrite. It reuses the existing Baymax owner session; there is no second login. FastAPI checks the signed session cookie on every `/guide` request, including CSS, JavaScript, images, and page navigation. Do not mount the generated directory without this middleware. The Render build installs `requirements-docs.txt` and runs `zensical build --strict`.

The Render-local source copy is under `apps/api/docs` and is required because the existing Render service root directory is `apps/api`. Keep it synchronized with the canonical repository-level `docs/` pages when editing documentation.

## Interactive API documentation

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | /docs | Public | Swagger UI for the generated OpenAPI contract |
| GET | /openapi.json | Public | Generated OpenAPI document |
| POST | /api/v1/diagnostics/gate-3 | Owner session required | Production NTP, Binance REST/WebSocket, and rollback-diagnostic checks |
| POST | /api/v1/diagnostics/gate-3/durable-snapshot | Owner session + explicit write confirmation | One-time durable snapshot commit and independent readback verification |
| GET | /api/v1/health | Public | Process liveness |
| POST | /api/v1/analysis/prepare | Owner session required | Prepare explicitly classified inputs; does not generate an answer |
| POST | /api/v1/analysis/respond | Owner session required | Classify a natural-language message, prepare verified inputs, run market intelligence, and return a structured Baymax assessment |
| POST | /api/v1/analysis/history | Owner session required | Retrieve bounded Binance Spot historical OHLCV and persist its provenance |
| POST | /api/v1/auth/login | Public; password and trusted Origin required | Verify the single owner password and set the session cookie |
| GET | /api/v1/auth/session | Public | Return only whether the request has a valid owner session |
| POST | /api/v1/auth/logout | Public; trusted Origin required | Clear the browser's owner session cookie |

Open http://127.0.0.1:8000/docs during local development or
https://baymax-api-6b49.onrender.com/docs for the deployed backend.
Select GET /api/v1/health, choose Try it out, then Execute to send a real
request to the backend and inspect its status, headers, and response body.

Swagger UI is an API explorer, not an authentication or authorization system. `/docs` and `/openapi.json` are public in production so the API reference can be opened without signing in. Protected operations—including analysis, historical-market retrieval, and both Gate 3 diagnostic endpoints—still enforce backend owner-session authentication. Unauthenticated diagnostic requests receive 401. Public documentation does not grant permission to execute protected operations. ReDoc remains disabled.


## Baymax AI intelligence (Groq)

Baymax uses Groq Chat Completions through the OpenAI-compatible endpoint. The
provider adapter is isolated in `app/ai/groq.py`; classification, response
generation, and orchestration are separate modules:

- `app/ai/classifier.py` maps the message to one of four explicit intents using
  a strict structured-output schema: educational, programming, current_market,
  or historical_market. Low-confidence or incomplete classifications request
  clarification and do not trigger market-data retrieval.
- `app/orchestration/requests.py` remains the authority for on-demand market
  retrieval. Only current_market reaches the Binance service.
- `app/ai/generator.py` receives the original message and prepared inputs. It
  must not invent missing prices, candles, indicators, volume, or trends.
  For market requests it also produces a structured JSON assessment
  (`generate_assessment`) that is schema-validated; its decision must agree
  with the deterministic safety gate or it is discarded.
- `app/ai/engine.py` connects those components in that order.
- `app/intelligence/` is the Gate 4 deterministic engine: pure-Python
  indicators (SMA/EMA/RSI/MACD/ATR/Bollinger/ADX/volume), trend, confirmed
  swing structure, support/resistance zones, volatility, and multi-timeframe
  alignment over verified closed-candle series.
- `app/market_data/analysis_input.py` assembles the verified five-timeframe
  input bundle (5m/15m/1h/4h/1d, 300 closed candles each) with per-series
  provenance.
- `app/strategy/` derives the deterministic BUY/SELL/WAIT scenario
  (entry zone, stop-loss, take-profits, risk/reward ≥ 1.5) and applies the
  fail-closed `DecisionSafetyGate` (3,000 ms price freshness, completeness,
  provenance, alignment checks).
- `POST /api/v1/analysis/respond` is owner-session protected and returns the
  generated answer, selected intent, symbol, market-data status,
  clarification flag, and — for market requests — a structured `assessment`
  object (decision, summary, evidence, risks, invalidation, limitations,
  alignment, data quality, deterministic scenario).

Configure these variables on the **Render backend only**:

| Variable | Required | Purpose |
|---|---|---|
| `GROQ_API_KEY` | Yes for AI responses | Private Groq API key |
| `GROQ_MODEL` | No | Defaults to `openai/gpt-oss-20b` |

Do not add the key to Vercel, frontend code, source control, or chat. The API
continues to start without a Groq key, but `/analysis/respond` returns 503
until one is configured. No paid plan or usage level is assumed; check the
current Groq account limits and pricing before relying on production usage.

The AI provider has a bounded request timeout and no automatic retry loop.
Provider failures return a generic service-unavailable response and never
expose the API key or raw provider error. Groq can be replaced later by
implementing the same small completion-client contract.

**Important current limitations:** production uses a background NTP clock-health monitor and remains fail-closed if at least two sources cannot agree within the configured offset and delay thresholds. Production NTP consensus has passed. The provenance migration `20261118_0005` is applied, and one production BTCUSDT snapshot was committed and independently read back from Supabase; see the Gate 3 evidence log. Full deployed-service WebSocket lifecycle recovery remains open. Historical OHLCV retrieval is available through the owner-only endpoint, and the frontend chat is connected to `/analysis/respond`; natural-language historical analysis remains follow-up work. The AI layer does not execute trades or have exchange tools.

## Tests and quality

    ruff format --check app tests
    ruff check app tests
    mypy app tests
    pytest

No live Supabase project or production secret is required to run the API unit tests.
The runtime API uses a dedicated PostgreSQL login supplied through
DATABASE_URL. Alembic requires a separate privileged connection supplied
through MIGRATION_DATABASE_URL; never configure that variable on the Render
web service or Vercel. The normal production migration path is the manually
approved GitHub Actions workflow documented in
[Secure production database migrations](../../docs/development/SECURE_MIGRATIONS.md).

## Deployment preparation

The repository-level render.yaml describes the Render web-service build,
start command and health-check path. It does not create a Render service or
authorize a deployment. Review the manifest and current Render plan limits
before manually creating a service.

The service root is apps/api; Python is pinned by .python-version.

## Database foundation (Gate 1)

The Supabase project uses PostgreSQL 17. Application objects belong in the
private baymax schema; do not create Baymax application tables in public.
The schema has explicitly revoked schema access for anon, authenticated, and
service_role; those API roles also have no privileges on Baymax tables.

Two non-login PostgreSQL privilege-group roles are created:

- baymax_app: non-login runtime privilege group.
- baymax_migrator: non-login migration privilege group.
- baymax_runtime: dedicated login inheriting baymax_app; configure only in Render.
- baymax_migration: dedicated login inheriting baymax_migrator; keep its credential
  in the private operator environment and use it only for Alembic.

The initial audit foundation creates baymax.audit_logs with UUID identity,
event and actor classification, optional resource/request references, JSONB
metadata, and a timezone-aware event timestamp. Metadata must be a JSON object.
The runtime role has SELECT and INSERT only; UPDATE and DELETE are not granted,
so normal application operations cannot rewrite or erase audit history. Never
place passwords, API keys, tokens, or other secrets in audit metadata.

No login password is embedded in source control. A dedicated login role should
be provisioned and granted membership in the appropriate group only when the
Render database connection is configured. Keep the database URL in Render
environment variables, never in Vercel or frontend variables.

### Alembic

Alembic revisions live in alembic/versions. The Alembic version table is
stored in baymax.alembic_version. The initial revision is intentionally
idempotent so the repository migration history can be initialized against the
already-provisioned foundation.

Set DATABASE_URL on Render to a Supabase shared **session-pooler** connection
(port 5432) authenticated as `baymax_runtime`. Render's outbound network is
IPv4-only, while Supabase's direct endpoint is IPv6-only on the free plan. For
a custom role, the session-pooler username is `baymax_runtime.<project-ref>`.
Copy the exact pooler host from Supabase Dashboard → Connect → Session pooler;
do not guess the pooler cluster hostname. Do not use transaction mode (port
6543) for this persistent SQLAlchemy connection.

The runtime engine uses SQLAlchemy 2.x with psycopg 3,
connection pre-ping, a bounded pool, and TLS required by default. Startup
verifies connectivity with SELECT 1; it never logs the connection URL or
password. Request handlers can obtain a request-scoped SQLAlchemy Session via
the get_db_session dependency in app.db.session.

Store MIGRATION_DATABASE_URL only as the GitHub `baymax-production`
environment secret for the manually dispatched migration workflow, using a
connection authenticated as baymax_migration. Never place it on the Render
web service, Vercel, or in the frontend. Keep the local PowerShell script as
a controlled fallback for diagnostics and recovery. The Alembic environment automatically
selects psycopg 3 for postgresql:// and postgres:// URLs. Use the Supabase
session pooler or a direct connection appropriate for migrations; do not use
a transaction-pooler URL for schema migration operations.

The two login roles are separate PostgreSQL identities. baymax_runtime inherits
only baymax_app; baymax_migration inherits only baymax_migrator. Do not reuse
the Supabase postgres owner credential for either connection.

Production migrations run through GitHub Actions → Supabase production
migrations after the migration code is merged to main and the operator types
`APPLY`. See [the secure migration runbook](../../docs/development/SECURE_MIGRATIONS.md).

For controlled local recovery only, run from apps/api:

    alembic upgrade head

The public health endpoint remains a process-liveness check only and does not
depend on database availability. No private database endpoint is exposed in
this gate.

### Database conventions

- Schema-qualify application objects under baymax.
- Use PostgreSQL-native UUID identifiers generated with gen_random_uuid().
- Store instants as timezone-aware timestamptz in UTC.
- Use explicit named constraints and indexes.
- Use jsonb only for intentionally flexible structured payloads.
- Add explicit grants and RLS decisions alongside each future table migration.
- Do not grant Supabase API roles access to Baymax tables by default.
- Preserve migration history; do not edit a migration after it has been applied.
- Destructive downgrade operations must not silently delete retained trading or
  learning history.


### Historical candle retrieval

The owner-only `POST /api/v1/analysis/history` endpoint retrieves Binance Spot
OHLCV candles for an explicit symbol, interval, and timezone-aware range.
It validates OHLC relationships, decimal volumes, trade counts, UTC interval
alignment, and close-time semantics. Requests are bounded to 10,000 candles,
with Binance pagination capped at 1,000 rows per REST request.

Missing intervals are detected against the expected candle-open schedule and
retried in up to two bounded recovery passes. The response exposes
`complete` and `missing_open_times`; unrecovered gaps are never filled with
synthetic data. Forming candles are explicitly marked as not closed. Historical
data retrieval does not alter the current-price 3-second freshness rule.

This structured endpoint is the backend foundation for historical analysis.
The frontend chat is connected to `/analysis/respond`; natural-language
historical analysis inside that pipeline remains follow-up work.
