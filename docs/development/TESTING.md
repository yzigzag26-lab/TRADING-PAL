# Testing and quality checks

The supporting foundation must be testable from a clean checkout and must not
require production credentials or a live Supabase project.

## Backend foundation

From `apps/api` with Python 3.12 and the development extra installed:

```bash
ruff format --check tests
ruff check tests
mypy tests
pytest
```

These tests validate repository configuration, environment-variable inventory,
Python runtime alignment, and documentation setup. They do not claim to test
FastAPI endpoints, authentication, database behaviour, or trading logic that
has not yet been implemented.

## Documentation

From the repository root:

```bash
python -m pip install -r requirements-docs.txt
zensical build --strict
```

Strict mode must fail on broken internal links and validation issues. Fix the
source rather than suppressing a valid warning.

## Frontend

From `apps/web`:

```bash
npm install
npm run lint
npm run typecheck
npm run build
```

A check that was not run must be reported as **not run**, with its reason.
