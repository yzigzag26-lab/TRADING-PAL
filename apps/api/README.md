# Baymax API

The backend now contains the first Phase 1 application milestone: a Python 3.12
FastAPI service with a public liveness endpoint, strict CORS allow-list,
request correlation, structured JSON logs, and a consistent error envelope.

Authentication, database access, profiles, preferences, AI, market data and
trading operations are not implemented in this stage.

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

No live Supabase project or production secret is required for this stage.

## Deployment preparation

The repository-level `render.yaml` describes the Render web-service build,
start command and health-check path. It does not create a Render service or
authorize a deployment. Review the manifest and current Render plan limits
before manually creating a service.

The service root is `apps/api`; Python is pinned by `.python-version`.
