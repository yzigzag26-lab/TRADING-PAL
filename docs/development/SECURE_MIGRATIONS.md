# Secure production database migrations

Baymax applies production Alembic migrations through a manually dispatched
GitHub Actions workflow. The privileged database credential is stored as a
GitHub **environment secret**, not in the repository, Render, Vercel, or the
frontend.

## One-time GitHub setup

1. Open the repository's **Settings → Environments**.
2. Create an environment named `baymax-production`.
3. Add an environment secret named `MIGRATION_DATABASE_URL`.
4. Set its value to the complete PostgreSQL session-pooler connection URL
   authenticated as `baymax_migration`. Use the exact Supabase Session Pooler
   host and port 5432 already verified for this project. Do not use the
   transaction pooler (6543).
5. If GitHub offers required reviewers for this repository and plan, configure
   an approval requirement for the `baymax-production` environment.

Do not put the migration URL in a repository-level secret, GitHub variable,
Render environment, Vercel environment, workflow file, issue, pull request,
or chat. Do not print it in workflow logs. Rotate the database role password
only when there is a security reason or credential compromise, then update
this environment secret.

## Running a production migration

1. Merge the migration code and its tests into `main`.
2. Open **Actions → Supabase production migrations → Run workflow**.
3. Select `main`.
4. Set `target` to `head`.
5. Type `APPLY` in the confirmation field.
6. Run the workflow and approve the `baymax-production` environment gate if
   one is configured.
7. Review the run log. It prints the current revision, available Alembic
   heads, applies `alembic upgrade head`, and prints the resulting revision.

The workflow is manual-only. It does not run on pushes, pull requests, Render
deployments, or Vercel deployments. It refuses to run from a branch other than
`main`, requires the exact `APPLY` confirmation, serializes production
migration runs, and fails if the environment secret is missing.

## Credential boundaries

- `MIGRATION_DATABASE_URL`: GitHub `baymax-production` environment secret,
  available only to the migration step after the environment gate.
- `DATABASE_URL`: Render runtime connection authenticated as
  `baymax_runtime`; never use it for Alembic.
- Vercel: no database migration credential.
- Local PowerShell migration script: remains available for controlled local
  diagnostics or recovery, but is no longer the normal production path.

A successful workflow run confirms Alembic completed and reports the current
revision. It does not replace application-level verification of new policies,
grants, or runtime behavior. Run the Supabase security advisor and targeted
read-only SQL checks after security-sensitive migrations.
