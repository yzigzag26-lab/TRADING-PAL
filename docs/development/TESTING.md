# Testing and quality checks

The backend foundation must be testable from a clean checkout and must not
require production credentials or a live Supabase project.

## Backend

From apps/api with Python 3.12 and the development extra installed:

    ruff format --check app tests
    ruff check app tests
    mypy app tests
    pytest

The first application tests cover the liveness contract, generated OpenAPI,
Swagger UI availability and its OpenAPI document link, disabled ReDoc,
CORS allow-list behaviour, request correlation, and safe error envelopes.
They do not claim to test authentication, database behaviour, or trading logic
that has not yet been implemented.

## Documentation

From the repository root:

    python -m pip install -r requirements-docs.txt
    zensical build --strict

Strict mode must fail on broken internal links and validation issues. Fix the
source rather than suppressing a valid warning.

## Frontend

From apps/web:

    npm install
    npm run lint
    npm run typecheck
    npm run build

A check that was not run must be reported as **not run**, with its reason.
