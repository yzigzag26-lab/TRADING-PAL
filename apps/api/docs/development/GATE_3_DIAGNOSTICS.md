# Gate 3 — Production market-data diagnostics

## Purpose

The production diagnostic runs inside the deployed Baymax API process. It is
owner-session protected and is separate from the public liveness endpoint.
It does not expose environment variables, exchange credentials, connection
strings, or raw exception messages.

## Run

After the backend change has been deployed, sign in to the Baymax owner
frontend so the browser has the existing owner session cookie. Then send:

```http
POST /api/v1/diagnostics/gate-3
```

No request body is required. The endpoint returns one result for each check.
It returns HTTP 200 when all checks pass and HTTP 503 when one or more checks
fail. The public `/api/v1/health` endpoint remains a lightweight liveness
check and does not run these diagnostics.

## Checks

- **NTP clock:** forces a fresh consensus check using the configured independent
  NTP sources and reports source count and measured offset.
- **Binance Spot REST:** requests the latest public BTCUSDT trade from the
  deployed Render process and validates its timestamp and positive price.
- **WebSocket reconnect:** opens a public BTCUSDT trade stream, receives and
  validates a fresh event, closes that stream, then opens a second independent
  stream and receives another fresh event. This verifies that the deployed
  process can reconnect after a closed subscription. Automated unit tests
  separately cover the stream adapter's retry and recovery behavior after
  transport failures.
- **Snapshot INSERT/SELECT:** uses the runtime database session to insert a
  marked diagnostic row, reads it back inside the same transaction, and then
  always rolls the transaction back.

## Snapshot safety boundary

The snapshot table is append-only and the runtime role is not granted DELETE.
The diagnostic therefore does **not** commit a production test row. It proves
that the runtime can execute INSERT and SELECT within one transaction, but it
does not prove durable commit visibility across transactions. The response
states this explicitly with `durable_commit_verified: false`. Durable commit
verification requires a separately approved cleanup or staging strategy and
must not be inferred from this endpoint.

## Security and operating limits

- The endpoint requires the existing signed owner session.
- The diagnostic uses only public Binance Spot endpoints; no API key is used.
- No order, account, balance, or trading endpoint is called.
- REST and WebSocket operations have explicit timeouts.
- Database writes are rolled back; no migration or schema change is performed.
- Do not expose this endpoint through unauthenticated monitoring or publish its
  response publicly.
