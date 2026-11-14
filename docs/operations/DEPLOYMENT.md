# Deployment operations

This is an operational guide, not authorization to provision services or deploy
the backend. The owner must approve account changes, production secrets, and
release actions.

## Hosting targets

- Frontend: Vercel, project root `apps/web`.
- Backend: Render, Python 3.12 + FastAPI, service root `apps/api`.
- Database and identity: Supabase; not connected in the current backend stage.
- Engineering documentation: local build and CI. A public docs host is not
  selected.

## Render configuration

The repository-level `render.yaml` prepares a single web service with:

- Python version from `apps/api/.python-version`.
- Root directory `apps/api`.
- Build command: `python -m pip install .`.
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- Health check: `/api/v1/health`.
- Free plan declaration; confirm current availability and limits before use.

The manifest does not create a Render service, connect an account, or trigger a
deployment. The owner must review the plan and authorize service creation.
Do not add secrets to the manifest.

## Backend release checklist

1. Review the exact commit and all CI results.
2. Confirm the FastAPI app and liveness contract are implemented.
3. Confirm Python 3.12.16 and approved start/build commands.
4. Review current Render free-tier limits and cold-start behaviour.
5. Configure only the documented environment values in Render settings.
6. Confirm CORS contains the actual production frontend origin.
7. Create/deploy the service only after owner approval.
8. Verify the HTTPS health endpoint and record the deployed commit.

The current health check verifies process liveness only; it does not check
Supabase or any other external dependency.

## Rollback

Record the source commit, CI run, deployment result, and smoke-test outcome for
each release. If unhealthy, roll back to the last healthy deployment using the
provider's supported procedure and document the incident.
