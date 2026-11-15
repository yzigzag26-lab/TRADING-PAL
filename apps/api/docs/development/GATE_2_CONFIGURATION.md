# Gate 2 — Configuration schema

**Status:** Implemented on a feature branch; not yet merged or applied to the live database.

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
values must be greater than zero and at most 100. Quote-currency values must
be positive and require an explicit currency code. Position limits must be at
least one; leverage must be at least one. These are data-integrity bounds, not
recommended personal risk settings.

## Migration

Revision: `20261115_0003`  
Previous revision: `20261115_0002`

Run from `apps/api` with a trusted migration connection:

```bash
alembic upgrade head
```

Do not put `MIGRATION_DATABASE_URL` in Vercel or in the runtime frontend.
Use a trusted privileged migration connection and keep its value in a secure
local operator environment. The Render runtime should receive only a dedicated
login role that inherits `baymax_app`, not the migration credential.

The downgrade intentionally preserves the singleton settings rows. Do not
delete owner configuration as an incidental rollback operation.

## Verification

The backend CI suite checks:

- Private schema registration in SQLAlchemy metadata.
- Singleton constraints.
- Nullable/unset risk limits and absence of invented personal defaults.
- Numeric precision and units.
- Timezone-aware timestamps.
- Required check constraints and JSONB object types.

The migration still requires a real PostgreSQL application and post-migration
inspection before Gate 2 can be accepted.

## Security note — current Gate 1 tables

Supabase's advisor currently reports RLS disabled on
`baymax.audit_logs` and `baymax.alembic_version`. A direct privilege
inspection confirmed that `anon`, `authenticated`, and `service_role`
have neither schema USAGE nor table privileges, so those roles cannot access
these private-schema tables through the Data API at present. This is not a
reason to ignore defense in depth: RLS remains a hardening item that requires
an explicit policy decision before applying remediation to the live database.
