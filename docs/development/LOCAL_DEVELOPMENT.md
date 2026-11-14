# Local development

## Supported toolchain

- Python **3.12** for backend and documentation tooling.
- Node.js 22 and npm for the Next.js frontend.
- Git.

Python 3.12 is approved. Do not silently change the runtime or introduce a
different package manager.

## Backend foundation

From the repository root:

```bash
cd apps/api
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
pytest
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`. The API
application is not implemented in this foundation; there is no API server to
start yet.

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
