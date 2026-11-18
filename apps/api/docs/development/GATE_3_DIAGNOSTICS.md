# Gate 3 Production Diagnostics

## Purpose and access boundary

This procedure runs bounded production checks inside the deployed Baymax API
process. It is the operational smoke test for Gate 3 infrastructure; it is not
the public liveness check.

- Swagger UI at `/docs` and the OpenAPI schema at `/openapi.json` are public
  so the API reference can be opened without signing in.
- The production diagnostic operation
  `POST /api/v1/diagnostics/gate-3` remains owner-session protected.
- The durable persistence verification
  `POST /api/v1/diagnostics/gate-3/durable-snapshot` is also owner-session
  protected and requires an explicit confirmation body.
- Public Swagger access does **not** grant permission to execute either
  operation. Unauthenticated requests must receive HTTP `401`.
- The Zensical guide remains behind the existing private-guide authentication
  middleware.

Do not share an owner session cookie, session token, or diagnostic response
publicly.

## Before running the rollback diagnostic

1. Confirm the latest backend deployment containing the Gate 3 diagnostic
   endpoint is **Live** in the approved Render workspace.
2. Open Swagger through the owner frontend:
   `https://baymax-nu.vercel.app/docs`.
   The OpenAPI schema is available at
   `https://baymax-nu.vercel.app/openapi.json`. These frontend-domain routes
   proxy to Render, preserving the browser's frontend-domain owner session.
3. Sign in to Baymax through the owner frontend and ensure the browser has a
   valid owner session. The backend issues the signed, HttpOnly session cookie;
   do not attempt to copy it into source code or expose it.
4. In Swagger, expand **POST /api/v1/diagnostics/gate-3**, select **Try it out**,
   leave the request body empty, and select **Execute**.

The browser sends its frontend-domain cookie to the same-origin Next.js proxy.
The proxy forwards the cookie to Render, and the backend independently
validates the owner session before executing diagnostics. Opening Swagger
directly on the Render hostname will not carry the frontend-domain cookie.
If the response is `401`, sign in again through the owner flow; do not disable
the endpoint's authentication.

## Durable snapshot commit verification

The rollback diagnostic above intentionally does not prove durable persistence.
Use the separate endpoint below only when you deliberately want to create one
permanent audit record.

1. Confirm the latest backend deployment includes
   `POST /api/v1/diagnostics/gate-3/durable-snapshot`.
2. Keep the owner session active in the same browser and open
   `https://baymax-nu.vercel.app/docs`.
3. Expand **POST /api/v1/diagnostics/gate-3/durable-snapshot** and select
   **Try it out**.
4. Submit this exact JSON body:

   ```json
   {
     "confirm_durable_write": true
   }
   ```

5. Select **Execute** once. Do not retry automatically if the response is
   ambiguous; inspect the database first to avoid creating duplicate audit rows.

The endpoint executes the normal production path:

`BinanceMarketDataService` → `BaymaxRequestOrchestrator` →
`MarketDataProvenanceRepository.record_price()`.

The existing repository performs the INSERT and COMMIT using the configured
`baymax_runtime` database role. The endpoint then opens a new SQLAlchemy
session and a separate database transaction, selects the committed row by its
snapshot ID, and compares its values against the validated market input.

A successful HTTP `200` response must include:

- `durable_commit_verified: true`
- `separate_transaction_readback: true`
- A stable `snapshot_id` and request ID.
- `symbol: "BTCUSDT"`, `exchange: "BINANCE"`, `market: "SPOT"`.
- Exact decimal price and source/trade identifier.
- Binance market-event and exchange-event timestamps.
- Backend receive and validation timestamps, plus age at validation.
- Database `created_at` timestamp.

**This operation creates one permanent append-only snapshot on every successful
invocation.** The table has no update/delete cleanup path by design. Only run it
once for this acceptance check. If the endpoint returns an error after the
commit attempt, inspect `baymax.market_data_snapshots` for the request/snapshot
before trying again; an unsuccessful read-back does not prove that the commit
failed.

The endpoint does not write SQL directly, bypass RLS, elevate the runtime role,
change grants, or run a migration. It uses the same application ingestion and
provenance repository as current-market analysis.

## What the rollback diagnostic checks

The rollback endpoint executes the following checks from the deployed Render process:

| Check | What it verifies |
|---|---|
| `ntp_clock` | A fresh consensus check against the configured independent NTP sources. |
| `binance_spot_rest` | A public Binance Spot BTCUSDT latest-trade request, including positive price and event freshness validation. |
| `websocket_reconnect` | Opens a BTCUSDT trade stream, receives a fresh event, closes it, then opens a second independent stream. |
| `snapshot_insert_read_rollback` | Uses the runtime database role to insert a marked row and read it back within one transaction. The transaction is always rolled back. |

The endpoint uses public Binance market-data endpoints only. It does not use
Binance API credentials, private account endpoints, or trading operations.

## Interpret the rollback diagnostic response

HTTP `200` with top-level `status: "passed"` means every check in that run
passed its bounded live test. HTTP `503` means at least one check failed.
HTTP `401` means the request did not carry a valid owner session.

The snapshot rollback check returns:

- `insert_read_verified: true`
- `transaction_rolled_back: true`
- `durable_commit_verified: false`

It proves same-transaction INSERT/SELECT privileges only. It must not be
reported as durable persistence evidence.

## Gate 3 completion status

A successful rollback diagnostic and a successful durable snapshot verification
are separate pieces of operational evidence. Neither alone closes every Gate 3
acceptance criterion. The wider Gate 3 acceptance contract in
[Gate 3 Market Data](GATE_3_MARKET_DATA.md) still applies, including deterministic
tests, code review, deployed runtime checks, recovery, and data-quality evidence.

Record the deployment commit, deployment ID, diagnostic timestamp, HTTP status,
snapshot ID, and read-back result in the project evidence log. Never record
cookies, credentials, or other secrets.

## Security and operating limits

- Keep owner-session authentication on both diagnostic endpoints.
- Keep production session secrets server-side and never add them to Swagger
  examples, frontend bundles, repository files, or chat messages.
- Public Swagger documents the available API operations; it does not make
  protected operations public.
- Keep production DB access under the existing `baymax_runtime` role and RLS.
- The durable verification is a single explicit application-level write, not
  a general-purpose database write interface.
- Neither endpoint places orders or accesses Binance account, balance, wallet,
  transfer, margin, or futures endpoints.
