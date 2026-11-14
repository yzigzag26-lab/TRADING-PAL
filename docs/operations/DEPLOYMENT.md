# Deployment operations

This is an operational guide, not authorization to provision services or deploy
the backend. The owner must approve account changes, paid plans, production
secrets, and release actions.

## Hosting targets

- Frontend: Vercel, project root `apps/web`.
- Backend: Render, Python 3.12 + FastAPI target. The API application is not
  implemented by this supporting foundation.
- Database and identity: Supabase.
- Engineering documentation: local build and CI. A public docs host is not
  selected.

## Backend release checklist

1. Review the exact commit and all CI results.
2. Confirm the FastAPI application and health route are implemented.
3. Confirm Python 3.12 runtime and approved start/build commands.
4. Configure secrets in Render settings, never in Git.
5. Verify Supabase issuer/JWKS and database access configuration.
6. Restrict CORS to actual frontend origins.
7. Verify the health endpoint over HTTPS.
8. Record deployed commit and smoke-test evidence.

Do not deploy this foundation as a functioning API: it currently contains
package metadata and configuration tests only.

## Rollback

Record the source commit, CI run, deployment result, and smoke-test outcome for
each release. If unhealthy, roll back to the last healthy deployment using the
provider's supported procedure and document the incident.
