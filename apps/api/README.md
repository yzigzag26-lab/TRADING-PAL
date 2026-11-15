# Baymax API

The backend now contains the first Phase 1 application milestone: a Python 3.12
FastAPI service with a public liveness endpoint, strict CORS allow-list,
request correlation, structured JSON logs, and a consistent error envelope.

Authentication, profiles, preferences, AI, market data and trading operations
are not implemented yet. Gate 1 provisions the private PostgreSQL schema and
migration infrastructure; application data models are introduced in later gates.

## Local development

From this directory:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

On Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
$env:APP_ENV = "development"
$env:CORS_ALLOWED_ORIGINS = "http://localhost:3000,https://baymax-nu.vercel.app"
uvicorn app.main:app --reload
```

The API listens at `http://127.0.0.1:8000`.

## Implemented routes

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/api/v1/health` | Public | Process liveness only |
| GET | `/openapi.json` | Public | Generated OpenAPI document |

The health response deliberately does not claim that Supabase or any other
external dependency is healthy. Swagger UI and ReDoc are disabled. Scalar is
added in the API documentation stage.

## Tests and quality

```bash
ruff format --check app tests
ruff check app tests
mypy app tests
pytest
```

No live Supabase project or production secret is required to run the API unit tests.
Database migrations require a trusted PostgreSQL connection supplied through `DATABASE_URL`.

## Deployment preparation

The repository-level `render.yaml` describes the Render web-service build,
start command and health-check path. It does not create a Render service or
authorize a deployment. Review the manifest and current Render plan limits
before manually creating a service.

The service root is `apps/api`; Python is pinned by `.python-version`.


## Database foundation (Gate 1)

The Supabase project uses PostgreSQL 17. Application objects belong in the
private `baymax` schema; do not create Baymax application tables in `public`.
The schema is not part of the Supabase Data API exposed-schema list and has
explicitly revoked schema access for `anon`, `authenticated`, and
`service_role`.

Two non-login PostgreSQL privilege-group roles are created:

- `baymax_app`: runtime privilege group; schema usage only at foundation stage.
- `baymax_migrator`: migration privilege group; schema usage and create privileges.

No login password is embedded in source control. A dedicated login role should
be provisioned and granted membership in the appropriate group only when the
Render database connection is configured. Keep the database URL in Render
environment variables, never in Vercel or frontend variables.

### Alembic

Alembic revisions live in `alembic/versions`. The Alembic version table is
stored in `baymax.alembic_version`. The initial Supabase migration creates
the schema before Alembic is used. The initial revision is intentionally
idempotent so the repository migration history can be initialized against the
already-provisioned foundation.

Set `MIGRATION_DATABASE_URL` to a PostgreSQL connection string for a trusted,
privileged migration environment. The initial foundation revision manages
roles and schema privileges, so do not run it with the application runtime
role. Keep this privileged URL out of the Render runtime environment; use it
only in a controlled migration job or local operator environment. The Alembic
environment automatically selects psycopg 3 for `postgresql://` and
`postgres://` URLs. Use the Supabase session pooler or a direct connection
appropriate for migrations; do not use a transaction-pooler URL for schema
migration operations.

Run migrations from `apps/api`:

```bash
alembic upgrade head
```

The public health endpoint remains a process-liveness check only and does not
depend on database availability. No private database endpoint is exposed in
this gate.

### Database conventions

- Schema-qualify application objects under `baymax`.
- Use PostgreSQL-native UUID identifiers generated with `gen_random_uuid()`.
- Store instants as timezone-aware `timestamptz` in UTC.
- Use explicit named constraints and indexes.
- Use `jsonb` only for intentionally flexible structured payloads.
- Add explicit grants and RLS decisions alongside each future table migration.
- Do not grant Supabase API roles access to Baymax tables by default.
- Preserve migration history; do not edit a migration after it has been applied.
- Destructive downgrade operations must not silently delete retained trading or
  learning history.
