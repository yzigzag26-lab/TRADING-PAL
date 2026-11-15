# Local development

## Supported toolchain

- Python **3.12** for backend and documentation tooling.
- Node.js 22 and npm for the Next.js frontend.
- Git.

Python 3.12 is approved. The API deployment is pinned to Python 3.12.16,
the current security release in the approved 3.12 series. Do not silently
change the runtime or introduce a different package manager.

## Backend

From the repository root:

```bash
cd apps/api
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

On Windows PowerShell:

```powershell
cd apps/api
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
$env:APP_ENV = "development"
$env:CORS_ALLOWED_ORIGINS = "http://localhost:3000,https://baymax-nu.vercel.app"
uvicorn app.main:app --reload
```

The API listens at `http://127.0.0.1:8000`. Set `APP_ENV` and `CORS_ALLOWED_ORIGINS` in the shell before starting the server; the app intentionally does not load secret files implicitly. The public liveness endpoint is
`/api/v1/health`; the generated OpenAPI document is `/openapi.json`.
Swagger UI and ReDoc are disabled. Scalar is introduced in the API docs stage.

The current health endpoint reports process liveness only. It does not assert
that Supabase or any external dependency is reachable.

## Frontend

```bash
cd apps/web
npm install
npm run dev
```

Vercel should use `apps/web` as its project root. Only browser-safe values may
be placed in `NEXT_PUBLIC_*` variables.

## Engineering documentation

From the repository root, install the pinned documentation dependencies and
start the local preview:

```bash
python -m pip install -r requirements-docs.txt
zensical serve
```

Build with validation before submitting changes:

```bash
zensical build --strict
```
