# Gate 2 — Configuration schema

**Status:** Implemented and applied to the live database. The approved production migration workflow completed successfully on 2026-11-16; its post-upgrade Alembic check reported `20261116_0004 (head)`. See [GitHub Actions run 43908646438](https://github.com/yzigzag26-lab/TRADING-PAL/actions/runs/43908646438). A direct SQL inspection of `pg_policies`, grants, and role membership should still be included in the next security preflight; workflow success proves the migration ran, not that every runtime authorization path has been independently exercised.

## Purpose

Gate 2 adds the two approved singleton configuration records in the private
`baymax` schema:

- `baymax.app_settings`: timezone, optional display currency, default exchange,
  general JSONB settings, and UTC timestamps.
- `baymax.risk_settings`: maximum risk per trade, maximum daily loss,
  maximum open positions, maximum leverage, optional quote currency, additional
  JSONB settings, and UTC timestamps.

Both tables enforce a single row with `id = 1`. The migration seeds the rows
idempotently and grants the runtime privilege-group role only SELECT, INSERT,
and UPDATE. It does not grant DELETE or any access to Supabase's
`anon`, `authenticated`, or `service_role` roles.

## Safe initial state

- Application timezone defaults to `UTC`.
- Default exchange is `BINANCE`, the approved initial market-data exchange.
- Display currency remains NULL until the owner selects one.
- Every personal risk limit remains NULL until the owner explicitly configures
  it. NULL means **not configured**, not zero and not unlimited.
- Risk limits are never inferred from user behaviour or changed by learning.
- A future risk evaluator must fail closed when a required limit is unset; it
  must not manufacture a value or treat a missing limit as permission.

Risk amounts carry an explicit unit: `percent` or `quote_currency`. Percent
values must be greater than zero and at most 100. Quote-currency values must be
positive and require an explicit currency code. Position limits must be at
least one; leverage must be at least one. These are data-integrity bounds, not
recommended personal risk settings.

## Migrations

- `20261115_0003` — singleton application and risk configuration.
- `20261116_0004` — RLS hardening for the two configuration tables.

Run from `apps/api` with a trusted migration connection:

```bash
alembic upgrade head
```

The production migration workflow completed successfully on 2026-11-16.
Its log shows the database at `20261116_0004 (head)` before and after
`alembic upgrade head`. See [workflow run 43908646438](https://github.com/yzigzag26-lab/TRADING-PAL/actions/runs/43908646438).

Do not put `MIGRATION_DATABASE_URL` in Vercel or in the runtime frontend.
Use a trusted privileged migration connection and keep its value in a secure
operator environment. The Render runtime should receive only a dedicated
login role that inherits `baymax_app`, not the migration credential.

The downgrade intentionally preserves the singleton settings rows. Do not
delete owner configuration as an incidental rollback operation.

## RLS migration — applied

Migration `20261116_0004` enables RLS on both configuration tables and adds
SELECT, INSERT, and UPDATE policies for `baymax_app`. The runtime login
`baymax_runtime` inherits that role. No DELETE policy is added, and existing
table grants remain unchanged.

The migration intentionally does not FORCE RLS: the dedicated migration
login owns the tables and PostgreSQL table owners bypass RLS by default.
The migration credential remains a privileged operator secret. The migration
has a non-destructive downgrade that removes only its policies and returns
the two tables to their previous RLS-disabled state.

The migration's successful application is confirmed by the production
workflow and Alembic revision output. Before relying on RLS as the only
protection for any future endpoint, inspect live `pg_policies`, grants, and
role membership and exercise the runtime login's SELECT/INSERT/UPDATE
permissions. RLS remains defense in depth alongside the private schema and
backend authorization.

## Verification

The backend CI suite checks:

- Private schema registration in SQLAlchemy metadata.
- Singleton constraints.
- Nullable/unset risk limits and absence of invented personal defaults.
- Numeric precision and units.
- Timezone-aware timestamps.
- Required check constraints and JSONB object types.
- The RLS migration's table targets, policy roles/actions, lack of DELETE
  policy, non-FORCE behaviour, and non-destructive downgrade.

Production acceptance includes the successful migration workflow, the
post-upgrade Alembic revision, and a live policy/grant inspection before
future data-access features depend on these controls.

## Security note — Gate 1 tables

Supabase's advisor previously reported RLS disabled on
`baymax.audit_logs` and `baymax.alembic_version`. A direct privilege
inspection at that time confirmed that `anon`, `authenticated`, and
`service_role` had neither schema USAGE nor table privileges. Re-run the
privilege and policy inspection before treating this as current evidence.
This is not a reason to ignore defense in depth.
