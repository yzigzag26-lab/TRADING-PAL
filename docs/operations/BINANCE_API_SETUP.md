# Binance Spot public market-data setup

**Purpose:** Document Baymax's approved connection to Binance Spot public market data for Gate 3.

**Baymax is a private, single-owner AI.** Gate 3 uses public market data only. It does not connect to your Binance account.

## 1. No API key or secret is required

Binance Spot public market-data endpoints have security type `NONE`. They do not require an API key, API secret, request signature, or account permissions.

For Gate 3:
- Do not create a Binance API key for Baymax.
- Do not send Binance credentials in chat or configure them in Render, Vercel, or local environment files.
- Do not enable trading, withdrawal, transfer, margin, futures, or private account permissions.
- Do not call private account or user-data endpoints.

This keeps the integration simple and removes an unnecessary credential-handling risk.

## 2. Approved market-data-only hosts

Use the Binance-documented public market-data-only hosts:

| Transport | Base URL | Purpose |
|---|---|---|
| REST | `https://data-api.binance.vision` | Historical candles, snapshots, verification and recovery |
| WebSocket | `wss://data-stream.binance.vision` | Live public Spot market streams |

Do not configure private trading or account API hosts for Gate 3.

## 3. Expected data flows

The backend will own the Binance connection:
- WebSocket is the primary transport for live updates.
- REST is used for historical candles, snapshots and recovery.
- A validated backend cache may be reused only while its underlying price event remains within the approved three-second age limit.
- If fresh data cannot be verified, Baymax reports it unavailable. It must not present stale cache as current.

The complete rules and acceptance tests are in [Gate 3 — Binance Spot market data freshness and reliability](../development/GATE_3_MARKET_DATA.md).

## 4. Rate limits and connection handling

- REST request weights and limits are IP-based and endpoint-specific.
- Monitor Binance response headers and current exchange metadata.
- Back off on HTTP 429 and respect `Retry-After`.
- Stop requests during an HTTP 418 ban until the indicated time.
- WebSocket connections have documented lifetime, ping/pong and message limits; implement planned reconnect and recovery.
- Do not poll REST repeatedly for every Baymax question when a fresh live snapshot is available.

## 5. Security

- No Binance API credentials are used by Gate 3.
- Keep any future private-account or trading integration out of this module.
- Never log secrets, cookies or private session material.
- Do not add paid providers or infrastructure without explicit owner approval.
- Public exchange data must still be timestamped, validated and labelled with its source.

## Official references

- [Binance Spot REST API](https://developers.binance.com/en/docs/products/spot/rest-api)
- [Binance Spot WebSocket Streams](https://developers.binance.com/en/docs/products/spot/web-socket-streams)
- [Binance Spot market-data-only FAQ](https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md)
