# Baymax API

The backend now contains the first Phase 1 application milestone: a Python 3.12
FastAPI service with a public liveness endpoint, strict CORS allow-list,
request correlation, structured JSON logs, and a consistent error envelope.

Authentication is implemented with the private single-owner session. Gate 1
provisions the private PostgreSQL schema and migration infrastructure. Gate 2
adds singleton application and risk configuration models; market data,
intelligence, evaluation, learning and memory remain later gates.

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
| GET | /docs | Public for the current foundation | Swagger UI with interactive Try it out |
| GET | /openapi.json | Public for the current foundation | Generated OpenAPI document |
| GET | /api/v1/health | Public | Process liveness only |

Open http://127.0.0.1:8000/docs during local development or
https://baymax-api-6b49.onrender.com/docs for the deployed backend.
Select GET /api/v1/health, choose Try it out, then Execute to send a real
request to the backend and inspect its status, headers, and response body.

Swagger UI is an API explorer, not an authentication or authorization system.
The documentation and OpenAPI schema are currently public because the only
implemented operation is the public liveness endpoint. Before any private
endpoint is introduced, Swagger UI and the OpenAPI document must be protected
behind the backend authentication boundary or disabled in production. Do not
publish private schemas or enable unauthenticated Try it out for private
operations. ReDoc remains disabled.

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
