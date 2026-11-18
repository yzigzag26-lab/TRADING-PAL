# Trading Pal

Trading Pal is the repository name for **Baymax**, a private, single-owner,
mobile-first cryptocurrency trading-intelligence assistant.

Version 1 is analysis-oriented. It is designed to retrieve verified Binance
Spot market data, interpret charts, calculate deterministic indicators,
synthesize evidence, and produce conditional scenarios with uncertainty and
invalidation. It does not execute trades.

## Repository layout

- `apps/web` — Next.js + TypeScript frontend.
- `apps/api` — Python 3.12 + FastAPI backend.
- `docs` — canonical architecture, implementation and operations docs.
- `apps/api/docs` — Render-local documentation source for the private,
  owner-authenticated `/guide/` site. Keep it synchronized with `docs/`.

## Current implementation status

### Frontend

- The private password screen is connected to the backend's single-owner
  login, session-restoration and logout endpoints.
- The authenticated workspace contains Dashboard, Markets, Chart Analysis,
  Risk Centre, History and Settings views.
- Market discovery, live market data, analysis chat responses and persistent
  history are not yet connected to the backend. The interface must continue
  to show unavailable/empty states rather than fabricated records.

### Backend

- Single-owner Argon2id password authentication and signed secure session.
- PostgreSQL foundation, application/risk configuration and approved
  migration workflow.
- Binance Spot public read-only current-price ingestion with the approved
  3,000 ms price-event freshness boundary and fail-closed validation.
- Production NTP clock-health monitor. Current-market analysis remains
  blocked when clock consensus is missing, stale or outside policy.
- Groq-backed intent classification and response generation. Configure
  `GROQ_API_KEY` on Render only; never expose it to Vercel or browser code.
- Binance Spot historical OHLCV retrieval through the owner-only
  `POST /api/v1/analysis/history` endpoint. The implementation validates
  decimal OHLCV fields, timestamps and interval boundaries; bounds requests
  to 10,000 candles; paginates at 1,000 rows; detects gaps; and performs up to
  two recovery passes. Incomplete series remain explicitly incomplete and
  missing candles are never synthesized.

### Gate 3 — market-data freshness and reliability

**Gate 3 is in progress, not complete.** Historical retrieval is merged, but
these acceptance items remain open:

- Persistent market-data provenance and exact snapshot references from
  analysis responses.
- WebSocket lifecycle evidence: planned reconnect before the 24-hour
  connection limit, disconnect health transitions, resubscription, duplicate
  and out-of-order event handling, and recovery verification.
- Live Binance Spot payload smoke test.
- Production Render verification of NTP reachability and clock consensus.
- Remaining acceptance evidence in
  [the Gate 3 contract](docs/development/GATE_3_MARKET_DATA.md).

A successful connection or a green CI run alone does not complete Gate 3.
The binding acceptance criteria require reproducible test and operational
evidence.

### Later implementation gates

- Natural-language historical-range extraction and historical analysis in
  Baymax's `/api/v1/analysis/respond` pipeline.
- Frontend chat integration with the real authenticated backend response.
- Analysis evaluation and quality measurement.
- Evidence-based learning and curated persistent conversation memory.

Market prices, candles, balances, signals, analyses and history must never be
fabricated. No Binance API key, account endpoint, trading permission, order
execution or paid market-data provider is part of the approved Gate 3 scope.

## Development

- Frontend: [apps/web/README.md](apps/web/README.md)
- Backend: [apps/api/README.md](apps/api/README.md)
- Phase 1 foundation handoff: [docs/IMPLEMENTATION_HANDOFF.md](docs/IMPLEMENTATION_HANDOFF.md)
- Engineering documentation index: [docs/index.md](docs/index.md)
- Gate 3 acceptance contract: [docs/development/GATE_3_MARKET_DATA.md](docs/development/GATE_3_MARKET_DATA.md)

## Security

Never commit credentials. Never expose database passwords, session-signing
secrets, migration credentials, or private provider keys to the browser or Git
history. Binance Gate 3 access uses public Spot market-data endpoints and
requires no Binance API key or secret.
