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

**Gate 3 remains incomplete; applicable criteria are being verified individually.**
Production evidence records NTP/REST smoke checks, a durable BTCUSDT snapshot
commit with independent Supabase readback, and the G3-05 forced five-second
WebSocket rotation/recovery diagnostic. G3-06 trade-sequence integrity and
G3-07 candle integrity are merged with deterministic CI evidence. G3-08 is
not applicable because no local depth book is implemented. G3-09 bounded REST
retry handling is merged in PR #42. G3-10 cache freshness enforcement is
merged in PR #44 (commit
`84059a6783d6eff0193549270c64212b7a5b4d7b`) and passed Backend and
Documentation CI on its exact PR head: Ruff format/lint, mypy, 168 pytest
tests (1 warning), and strict Zensical build.

G3-11 snapshot-to-audit linkage was implemented in PR #46 and merged to `main`
as commit `327faa7172171848930abc8884dfc79b76537c8f`. Current-price and
historical snapshots are linked to append-only audit rows in the same database
transaction, with request and snapshot identity; persistence failure blocks
market-dependent analysis.

G3-12 decision-safety enforcement was implemented in PR #54 and merged to
`main` as commit `e43620fb2cce89b87d9e5c6fed6254d831544cea`. A final
backend gate revalidates freshness, source/symbol/trade identity, timestamp
consistency and snapshot/audit provenance immediately before AI generation.
Incomplete historical series, unresolved gaps and open candles cannot be
accepted as complete decision inputs; unsafe requests stop before the
generator is called. Educational/programming responses remain available.
Trade recommendations are intentionally blocked until Baymax has a complete,
validated historical-candle and strategy-evidence pipeline. Backend and
Documentation CI passed on exact PR head
`e73ccc289ae91d2af603bafd93dcc7111f30f4c3`: Ruff format/lint, mypy, pytest
and strict Zensical build.

**G3-11 and G3-12 are merged and CI-verified. G3-13 is now the next
implementation task:** perform the repository/configuration security and
scope review. See the [Gate 3 contract](docs/development/GATE_3_MARKET_DATA.md)
for acceptance requirements and evidence.

A successful connection or green CI run alone does not complete Gate 3.
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
- Archived Phase 1 planning baseline (historical, not current implementation instructions): [docs/IMPLEMENTATION_HANDOFF.md](docs/IMPLEMENTATION_HANDOFF.md)
- Engineering documentation index: [docs/index.md](docs/index.md)
- Gate 3 acceptance contract: [docs/development/GATE_3_MARKET_DATA.md](docs/development/GATE_3_MARKET_DATA.md)

## Security

Never commit credentials. Never expose database passwords, session-signing
secrets, migration credentials, or private provider keys to the browser or Git
history. Binance Gate 3 access uses public Spot market-data endpoints and
requires no Binance API key or secret.
