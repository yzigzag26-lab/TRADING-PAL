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


## Recorded production evidence — 2026-11-18

The owner completed the rollback diagnostic and the one-time durable snapshot
verification in production.

### Rollback diagnostic

At `2026-11-18T12:16:58.086502Z`, the owner-authenticated
`POST /api/v1/diagnostics/gate-3` returned HTTP 200 with `status: "passed"`.
NTP consensus passed with 3 healthy sources and an approximately 1.05 ms
reported offset. Binance Spot REST passed with a 2,103 ms trade-event age. The
WebSocket check established two independent connections and received a trade
ID on each, with the second connection established after the first was
closed. The snapshot INSERT/SELECT/ROLLBACK check passed and, as designed, did
not commit a row.

### Durable snapshot

At `2026-11-18T12:42:25.098361Z`, the explicit durable-write endpoint returned
`status: "passed"`, `durable_commit_verified: true`, and
`separate_transaction_readback: true`.

- Snapshot ID: `8398dd5e-5b3d-4986-8a32-b872d427d298`
- Request ID: `1784dd1f-3389-4b6b-a552-fc0db5028b7a`
- Symbol: `BTCUSDT`; exchange/market: `BINANCE / SPOT`
- Price: `63993.08000000`; trade ID: `6876603329`
- Source: `binance_spot_rest`; connection state: `REST_RECOVERY`
- Age at validation: `309 ms`; validation state: `VALIDATED`
- Database creation time: `2026-11-18T12:42:25.098361Z`

A separate read-only Supabase query selected the same row by snapshot ID and
request ID. The identifiers, payload, source, timestamps, age, validation and
connection states, and creation timestamp matched the API response. This
independently confirms that the committed row remained present. The
`REST_RECOVERY` state is expected because this snapshot came from REST, not a
healthy WebSocket event.

This operation created one permanent append-only audit row. Do not rerun it
just to repeat the test. The earlier rollback diagnostic remains a separate
non-durable check and must not be confused with this commit evidence.

### Next production check

G3-05 is the next production acceptance item: verify deployed-service
disconnect handling, planned reconnect/resubscription, and restored fresh
price acceptance. The two-connection smoke check above does not close the full
23-hour-50-minute planned-rotation/lifecycle requirement. Gate 3 remains open
until all mandatory criteria in the acceptance contract have evidence.


## Forced WebSocket rotation and service recovery diagnostic

The owner-only endpoint `POST /api/v1/diagnostics/gate-3/websocket-rotation`
exercises a separate instance of the real `BinanceMarketDataService` against
Binance's public Spot REST and WebSocket services. It deliberately configures
that diagnostic instance with a **5-second connection lifetime**, so the
normal 23-hour-50-minute rotation does not need to elapse.

Run it after the backend deployment containing this endpoint is **Live**:

1. Sign in through the Baymax owner frontend and open
   `https://baymax-nu.vercel.app/docs`.
2. Expand **POST /api/v1/diagnostics/gate-3/websocket-rotation**.
3. Select **Try it out**. No request body is required.
4. Select **Execute** and allow up to 40 seconds for the bounded test.

The diagnostic verifies, in order:

- The service accepts an initial fresh BTCUSDT WebSocket trade.
- The short-lived connection reaches its planned rotation deadline and closes.
- The service observes the disconnect and invalidates its stream cache.
- The stream adapter establishes a replacement WebSocket subscription.
- A new trade is accepted from that replacement connection.
- `get_current_price()` consumes and validates the post-reconnect event using
  the production 3,000 ms freshness boundary and the live NTP health assertion.

A successful HTTP `200` response with top-level `status: "passed"` is
production evidence for this forced-rotation run. The response includes the
initial and post-reconnect trade IDs, connection transition evidence, event
source, event age, and validated price. HTTP `503` means a lifecycle stage,
clock-health prerequisite, or freshness check failed; inspect the response
before retrying.

**Isolation and side effects:** the diagnostic creates and closes its own
`BinanceMarketDataService`. It does not mutate the application-owned service,
change the configured 23-hour-50-minute lifetime, write a database snapshot,
or use Binance credentials/private endpoints/trading operations. It is
owner-session protected. The endpoint must not be used as a load test; run one
diagnostic at a time.

This is a short-duration production exercise of the same planned-rotation code
path, not a claim that the deployed connection has remained alive for 23 hours
and 50 minutes. Deterministic lifecycle tests plus this production result are
the combined evidence. G3-05 remains open until the owner runs the endpoint
against the deployed backend and records its actual response and deployment.
