# Gate 3 Production Diagnostics

## Purpose and access boundary

This procedure runs bounded production checks inside the deployed Baymax API
process. It is the operational smoke test for Gate 3 infrastructure; it is not
the public liveness check.

- Swagger UI at `/docs` and the OpenAPI schema at `/openapi.json` are public
  so the API reference can be opened without signing in.
- The production diagnostic operation
  `POST /api/v1/diagnostics/gate-3` remains owner-session protected.
- Public Swagger access does **not** grant permission to execute the diagnostic.
  An unauthenticated request must receive HTTP `401`.
- The Zensical guide remains behind the existing private-guide authentication
  middleware. This change makes Swagger documentation public only.

Do not share an owner session cookie, session token, or diagnostic response
publicly.

## Before running the test

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

## Alternative: PowerShell request

Use this only in a browser/session environment where you can securely obtain
and use the already-issued owner session cookie. Do not paste a session token
into chat, commit it, or save it in a script. Swagger's **Try it out** flow is
the recommended method because the browser can attach the existing HttpOnly
cookie automatically.

The request has no JSON body:

```http
POST /api/v1/diagnostics/gate-3
```

## What the diagnostic checks

The endpoint executes the following checks from the deployed Render process:

| Check | What it verifies |
|---|---|
| `ntp_clock` | A fresh consensus check against the configured independent NTP sources. The result includes healthy source count and measured clock offset. |
| `binance_spot_rest` | A public Binance Spot BTCUSDT latest-trade request, including positive price and event freshness validation. |
| `binance_spot_websocket` | Opens a BTCUSDT trade stream, receives a fresh event, closes it, then opens a second independent stream and receives another fresh event. This verifies a new subscription after closing the first. Automated tests separately cover transport-failure retry/recovery. |
| `snapshot_insert_select` | Uses the runtime database role to insert a marked row and read it back within one transaction. The transaction is always rolled back. |

The endpoint uses public Binance market-data endpoints only. It does not use
Binance API credentials, private account endpoints, or trading operations.

## Interpret the HTTP response

### All checks pass

HTTP `200` with top-level `status: "passed"` means every check in this
diagnostic run passed its bounded live test. Review each item in `checks`,
including its `status`, `duration_ms`, `message`, and available
`metadata`.

This is strong production smoke-test evidence for the tested components at
the recorded `checked_at` time. It does not, by itself, close every Gate 3
acceptance criterion.

### One or more checks fail

HTTP `503` with top-level `status: "failed"` means at least one required
check failed. Inspect the individual `checks` entries and their safe
failure messages. A failed check reports the exception type, not raw
exception details or secrets.

Treat the affected production capability as unavailable until investigated
and a fresh diagnostic run passes. Do not bypass clock health, relax the
3,000 ms market-event freshness limit, or substitute fabricated market data.

### Authentication fails

HTTP `401` means the request did not carry a valid owner session. This is
expected for unauthenticated callers and confirms the diagnostic operation
remains protected. OpenAPI visibility does not change this boundary.

### Snapshot write semantics

The snapshot check returns metadata equivalent to:

- `insert_read_verified: true`
- `transaction_rolled_back: true`
- `durable_commit_verified: false`

This distinction is intentional. The check proves that the runtime database
role can perform INSERT and SELECT within the same transaction. It does **not**
prove that a committed row is visible in a later transaction. The test row is
rolled back, so the diagnostic does not leave a permanent production record.
Durable commit verification needs a separately approved strategy and must not
be inferred from this result.

## Result interpretation example

A successful response has this general shape (values below are illustrative,
not evidence from a real production run):

```json
{
  "status": "passed",
  "checked_at": "2026-11-18T10:00:00Z",
  "symbol": "BTCUSDT",
  "checks": {
    "ntp_clock": {
      "status": "passed",
      "duration_ms": 120,
      "message": "NTP clock check passed.",
      "metadata": {
        "healthy": true,
        "healthy_sources": 3,
        "offset_seconds": 0.012
      }
    },
    "binance_spot_rest": {
      "status": "passed",
      "duration_ms": 240,
      "message": "Binance Spot REST check passed."
    },
    "binance_spot_websocket": {
      "status": "passed",
      "duration_ms": 700,
      "message": "Binance Spot WebSocket check passed."
    },
    "snapshot_insert_select": {
      "status": "passed",
      "duration_ms": 90,
      "message": "Snapshot INSERT/SELECT check passed.",
      "metadata": {
        "insert_read_verified": true,
        "transaction_rolled_back": true,
        "durable_commit_verified": false
      }
    }
  },
  "snapshot_write_mode": "transaction_rolled_back"
}
```

Do not compare illustrative durations or timestamps with production expectations;
use the actual response from the current run.

## Gate 3 completion status

A successful diagnostic is one required piece of Gate 3 operational evidence.
It does not automatically mark Gate 3 complete. The wider Gate 3 acceptance
contract in [Gate 3 Market Data](GATE_3_MARKET_DATA.md) still applies, including
deterministic tests, code review, deployed runtime checks, and evidence for
recovery and data-quality behavior.

Record the deployment commit, deployment ID, diagnostic `checked_at`,
HTTP status, top-level status, and each check's status in the project evidence
log. Never record cookies, credentials, or other secrets.
