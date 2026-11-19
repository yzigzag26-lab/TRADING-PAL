# Gate 3 Production Diagnostics

This runbook describes owner-only production diagnostics for Gate 3. The
Swagger UI and OpenAPI schema are public, but diagnostic POST operations require
the Baymax owner session.

## Forced WebSocket rotation and recovery

After the backend deployment containing the endpoint is Live, open
[`/docs`](https://baymax-nu.vercel.app/docs) and execute:

`POST /api/v1/diagnostics/gate-3/websocket-rotation`

No request body is required. Allow up to 120 seconds for the diagnostic.

The diagnostic starts an isolated instance of the real
`BinanceMarketDataService` using Binance's public Spot REST and WebSocket
adapters. Only this diagnostic instance receives a forced five-second
connection lifetime; the application-owned stream retains its normal
23-hour-50-minute rotation.

A successful response (`HTTP 200`, `status: "passed"`) demonstrates:

- An initial BTCUSDT WebSocket trade was accepted.
- The first connection remained alive for the forced five-second lifetime
  before closing.
- The service observed the disconnect and established a replacement
  subscription.
- A different, fresh trade arrived over the replacement WebSocket.
- The normal `get_current_price()` consume-time validation accepted the
  post-reconnect event under the existing freshness and NTP-health checks.

A failed run returns `HTTP 503` with the failed lifecycle stage. Inspect that
response and the backend logs before retrying.

The diagnostic is owner-session protected and read-only. It does not modify
the running application's stream, change its normal rotation configuration,
write a database snapshot, or use Binance credentials, private endpoints, or
trading operations. Run one instance at a time; it is not a load test.

This short-duration test exercises the same planned-rotation code path but
does not claim that one connection remained open for 23 hours and 50 minutes.
G3-05 remains open until a successful response from the deployed service is
recorded alongside the deterministic lifecycle test evidence.
