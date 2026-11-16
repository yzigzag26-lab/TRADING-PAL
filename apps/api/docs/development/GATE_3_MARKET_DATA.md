# Gate 3 — Binance Spot market data freshness and reliability

**Specification:** Baymax Market Data Freshness & Reliability v1.0  
**Status:** Owner-approved acceptance contract; first transport/retrieval implementation slice is in review and Gate 3 remains incomplete.  
**Applies to:** Gate 3 of the private, single-owner Baymax system.  
**Exchange:** Binance Spot only.  
**Access:** Public market data, read-only.  
**Authority:** This document is the binding Gate 3 acceptance contract. A successful Binance connection alone is not completion.

## 1. Purpose and non-negotiable rule

Gate 3 provides Baymax with current, validated Binance Spot market data for later analysis. It establishes the data-integrity boundary that future analysis and autonomous-execution components must consume.

**Baymax must never represent stale, incomplete, contradictory, or unverified market data as current or trade-ready.** If required data cannot be verified, Baymax must report that fresh data is unavailable. It must not invent, interpolate, silently carry forward, or guess missing market values.

Baymax is private and single-owner. Do not design this gate as a public multi-tenant market-data service.

## 2. Owner-approved decisions

The following decisions are approved and binding:

| Decision | Approved requirement |
|---|---|
| Product | Private, single-owner Baymax AI |
| Exchange | Binance Spot only |
| Market-data access | Public endpoints and public market streams; read-only |
| Price freshness | A price event must be no more than **3 seconds old** when validated for use |
| Stale trading data | **Strict fail-closed:** refuse trading decisions until fresh data has been retrieved and verified |
| Trading/account permissions | No trading, withdrawals, transfers, margin, futures, or private account endpoints in Gate 3 |
| Paid providers/services | None; no paid service without separate owner approval |
| Acceptance | Every criterion in Section 11 must have test evidence; connection success is insufficient |

The 3-second approval applies to the market-price event age. It does not silently approve numerical freshness limits for every other data type. Candidate limits for candles, best bid/ask, and depth are listed as provisional in Section 5 and must be confirmed before they become hard-coded acceptance thresholds.

## 3. Binance access model — no API key for public market data

Gate 3 uses Binance's public Spot market-data-only interfaces:

- REST base URL: `https://data-api.binance.vision`
- WebSocket base URL: `wss://data-stream.binance.vision`

These market-data-only hosts are intended for public market data. The Spot REST security model defines `NONE` endpoints as public market data; they do not require an API key or secret. **Do not create, request, store, or configure a Binance API key or secret for Gate 3.**

Do not call private account, user-data, trading, wallet, transfer, margin, or futures endpoints. Do not add signing code or credential environment variables. If a future scope requires private account data or trading, it needs a separate architecture, security review, and explicit owner approval.

Use only documented Binance Spot endpoints and streams. Verify each endpoint's security type, response fields, timestamp semantics, and request weight against the official documentation during implementation.

## 4. Data transport and responsibilities

### WebSocket — primary live feed

Use Binance Spot public market streams for continuous updates. The backend owns the connection lifecycle and subscriptions. The private single-owner deployment should start with a centrally managed backend connection manager and a bounded in-process latest-data cache; do not add Redis, a queue, or a separate worker solely for this gate.

The manager must handle:
- Connection establishment and health monitoring.
- Server ping frames and prompt pong replies.
- Planned reconnect before the documented 24-hour connection lifetime ends.
- Server shutdown notifications and unexpected disconnects.
- Resubscription after reconnect.
- Detection of missing, delayed, duplicate, or out-of-order events where the stream provides identifiers.
- Recovery and reconciliation before marking data healthy again.

Binance Spot WebSocket documentation currently specifies a 20-second server ping interval, a one-minute pong deadline, a five-incoming-message-per-second limit (including ping/pong and control messages), up to 1,024 streams per connection, and up to 300 connection attempts per five minutes per IP. Treat these as exchange constraints, not targets. Keep subscription/control traffic low.

### REST — history, snapshots, verification, and recovery

Use REST for:
- Historical OHLCV candles.
- Initial order-book snapshots.
- Recovery of missing candle intervals.
- Verification/recovery after WebSocket interruption.
- Timestamped latest-trade retrieval when a REST fallback is needed to establish price-event age.

Do not use frequent REST polling as a substitute for a healthy WebSocket feed. Do not treat a timestamp-less REST response as proof that a price event is within the approved 3-second freshness limit.

### Cache and persistence

- Cache only validated data.
- Re-check age at the moment data is consumed; cache age at insertion is not enough.
- A cached price may be reused only while its underlying market event remains within the approved 3-second limit.
- Expired cache entries must not be returned as current.
- Persist the historical market records required by approved Baymax features and audit references. Do not persist every raw tick by default without a measured need and an explicit retention/storage decision.
- Cache is an efficiency mechanism, never a freshness bypass.

## 5. Freshness policy

### Approved hard threshold

**Price event maximum age: 3,000 milliseconds.**

Calculate age using a source-provided market-event timestamp and a synchronized UTC clock at the validation/use boundary:

`age_ms = validation_time_utc - market_event_time_utc`

For trade events, preserve both Binance event time and trade time; use the source-defined market/trade timestamp for market-event age and retain event time separately. For other stream types, use the timestamp semantics documented for that specific event. Never substitute Baymax's receive time for the exchange's event time.

A price is not fresh when:
- Its market-event age exceeds 3,000 ms.
- The source timestamp is absent or cannot be interpreted reliably.
- The timestamp is unreasonably in the future or system clock health is outside the configured tolerance.
- The source/connection state is unhealthy or the event fails validation.
- The event cannot be tied to the requested symbol and Binance Spot market.

For a market-dependent question, Baymax must obtain or validate a current snapshot when the question is asked. It must not answer a current-price question from an old historical cache. If the latest verified price is older than three seconds, report that current data is unavailable.

### Provisional thresholds — not yet owner-approved

The earlier design discussion suggested the following initial candidates. They are **not binding acceptance thresholds** until the owner explicitly approves them:

| Data type | Candidate target | Candidate stale boundary | Status |
|---|---:|---:|---|
| Best bid/ask | Under 1 sec | 3 sec | Provisional |
| Order book/depth | Under 1 sec | 3 sec | Provisional |
| Live candle update | Under 2 sec | 5 sec | Provisional |
| Historical closed candles | Source-verified | Gap/completeness rules | Integrity requirement; retention/freshness details to be finalized |

A candle's freshness must account for whether it is still forming. Binance kline payloads identify whether a candle is closed; an open candle is not invalid merely because it has not closed. Missing historical intervals must be detected and backfilled before the affected series is marked complete.

The implementation must centralize all freshness thresholds in one validated policy/configuration module. Do not scatter numeric age constants throughout the codebase. Do not silently promote provisional thresholds to approved policy.

## 6. Timestamp, clock, and provenance requirements

For every event or snapshot, preserve as applicable:
- Binance market-event/trade timestamp.
- Binance event-generation timestamp.
- Baymax receive timestamp.
- Baymax validation/processing timestamp.
- Exchange, market, symbol, stream/endpoint, and data type.
- Source connection state and validation result.
- Sequence/update identifiers where supplied.
- Calculated age at validation and at consumption.

Store instants in UTC using timezone-aware values. Monitor host clock synchronization and clock drift. A clock-health failure must prevent data from being declared fresh.

Each analysis must be traceable to the exact market snapshot or snapshot identifiers it consumed. Never log credentials or sensitive session values.

## 7. Integrity and recovery rules

### General validation

Reject or quarantine events with:
- Unexpected exchange, market, symbol, or data type.
- Non-numeric, non-finite, zero/negative prices where a positive price is required, or invalid quantities.
- Missing/unparseable required timestamps.
- Impossible candle relationships (`low <= open/close <= high` must hold).
- Duplicate or out-of-order events that cannot be safely handled.
- Unexplained sequence gaps where sequence IDs are provided.
- Contradictory values that cannot be reconciled against a fresh source snapshot.

Never convert missing data to zero. Never manufacture candles or price observations.

### Candles

- Validate symbol, interval, open time, close time, OHLC, volume and trade-count fields.
- Distinguish forming candles from closed candles.
- Detect missing intervals and recover them through REST.
- Do not mark a series complete while required intervals are missing or unverified.

### Order book

If depth data is implemented in Gate 3, follow Binance's documented local order-book procedure:
1. Open the depth stream and buffer events.
2. Obtain a REST depth snapshot.
3. Discard buffered events already covered by the snapshot.
4. Verify the first applicable event bridges the snapshot update ID.
5. Apply updates in sequence.
6. If an update gap is detected, invalidate the local book and rebuild from a new snapshot.

A successful WebSocket connection or REST snapshot alone does not establish a synchronized order book. Record the snapshot's finite depth limitation; do not imply that levels outside the snapshot are known.

### Reconnect and recovery

After any interruption:
- Mark affected live data unavailable/degraded immediately.
- Reconnect with bounded exponential backoff and jitter.
- Restore required subscriptions.
- Backfill missing candles and rebuild sequence-dependent books.
- Validate timestamps, sequence continuity, and completeness.
- Only then mark the affected data healthy.
- Re-run the analysis from the newly verified snapshot; do not automatically revive a previously blocked trading decision.

## 8. REST rate-limit and operational protection

Binance Spot REST request limits are IP-based and endpoint weights vary. The implementation must:
- Inspect current `exchangeInfo` rate-limit metadata and endpoint weights at implementation time.
- Observe `X-MBX-USED-WEIGHT-*` response headers.
- Maintain conservative request budgeting.
- Avoid polling endpoints for every question when a fresh WebSocket-backed snapshot is available.
- On HTTP 429, stop the affected request flow and back off according to `Retry-After`.
- On HTTP 418, stop requests until the indicated ban period has elapsed; do not retry aggressively.
- Use bounded retries with exponential backoff and jitter for transient network/service failures.
- Surface degraded/unavailable status instead of looping indefinitely.

Do not hard-code Binance rate limits from an old document. Exchange limits can change; the implementation and operational guide must reference current official documentation.

## 9. Consumption and fail-closed behaviour

Separate informational analysis from trade authorization:

- For a current-market question, use a freshly verified snapshot. If it is unavailable, say so; do not claim the last cached price is current.
- Historical or educational analysis may use explicitly labelled historical data when the question does not require a current market snapshot.
- **Trading-decision mode must refuse to authorize a decision whenever any required input is stale, missing, incomplete, contradictory, unverified, or has unhealthy source/clock state.**
- A stale-data warning is not permission to trade.
- After data recovers, refresh and re-run the full analysis. Never approve a previously blocked decision automatically.
- Future execution components must independently revalidate all required market inputs and deterministic risk constraints immediately before any order-submission attempt. This is future scope, not implemented in Gate 3.

Gate 3 itself has no order-placement, account, or trading capability.

## 10. Illustrative provenance record

The following is a schema illustration, not a real quote:

```json
{
  "exchange": "BINANCE",
  "market": "SPOT",
  "symbol": "BTCUSDT",
  "data_type": "trade",
  "price": "0",
  "market_event_timestamp": "2026-01-01T00:00:00.000Z",
  "exchange_event_timestamp": "2026-01-01T00:00:00.001Z",
  "received_timestamp": "2026-01-01T00:00:00.010Z",
  "validated_timestamp": "2026-01-01T00:00:00.012Z",
  "age_ms_at_validation": 12,
  "source": "binance_spot_websocket",
  "connection_state": "HEALTHY",
  "validation_state": "VALID"
}
```

Implementation must use decimal-safe price/quantity handling; the zero in this illustrative example is a placeholder, not a valid market price.

## 11. Gate 3 acceptance contract

Gate 3 is complete only when every applicable criterion below has reproducible evidence. Code presence or a successful connection is not sufficient.

| ID | Acceptance criterion | Required evidence |
|---|---|---|
| G3-01 | Binance Spot public market-data-only REST and WebSocket connections work without API credentials | Integration test and configuration review |
| G3-02 | Live price events preserve source timestamps and are validated against the 3-second maximum | Deterministic unit tests at boundary values (<=3,000 ms accepted; >3,000 ms rejected) |
| G3-03 | Every market-dependent current query obtains/revalidates a fresh snapshot | Service/API tests proving old cache is refreshed or rejected |
| G3-04 | Missing/untrusted timestamps and unhealthy clock state fail closed | Negative tests |
| G3-05 | WebSocket ping/pong, planned 24-hour reconnect, disconnect detection and resubscription work | Simulated connection lifecycle tests |
| G3-06 | Duplicate/out-of-order events and sequence gaps are detected/handled safely | Deterministic event-sequence tests |
| G3-07 | Candle OHLC, interval continuity and open/closed state are validated | Fixture-based candle and gap tests |
| G3-08 | If local depth book is implemented, snapshot/update-ID synchronization and gap rebuild work | Depth snapshot/stream reconciliation tests |
| G3-09 | REST 429/418, Retry-After, transient errors and bounded backoff are handled | Mock HTTP response tests |
| G3-10 | Cache cannot bypass freshness validation | Cache-expiry and consume-time age tests |
| G3-11 | Audit/provenance records identify source, timestamps, validation and snapshot used by analysis | Persistence/service tests |
| G3-12 | Stale, incomplete, contradictory or unverified required inputs block trading decisions | Fail-closed policy tests |
| G3-13 | No API secrets, trading/account endpoints, fabricated market data or paid provider were introduced | Repository/configuration/security review |
| G3-14 | Backend quality checks and strict documentation build pass | CI run linked to the reviewed commit |
| G3-15 | Live Binance smoke test verifies real payload parsing without being the sole test strategy | Recorded smoke-test result plus deterministic tests |

Any criterion not implemented or not tested must remain open. Skipped tests must state the reason, risk, and owner-approved follow-up. Gate 3 cannot be marked complete while a mandatory criterion is unverified.

## 12. Out of scope

- Live or paper order execution.
- Binance private account, balance, order, wallet, user-data or transfer endpoints.
- API-key creation, signing, or credential storage.
- Withdrawals, transfers, margin, futures or leverage controls.
- Other exchanges or secondary providers.
- Paid data subscriptions.
- Multi-tenant fan-out infrastructure.
- AI analysis, strategy generation, evaluation, learning, or curated memory (later gates).
- Autonomous trading (future phase requiring separate approval and independent execution safeguards).

## 13. Official Binance references

Re-check these official pages at implementation time; they may change:
- [Spot REST API — general information, request security, data sources and rate limits](https://developers.binance.com/en/docs/products/spot/rest-api)
- [Spot WebSocket Streams — connection rules, limits, subscriptions and local order-book synchronization](https://developers.binance.com/en/docs/products/spot/web-socket-streams)
- [Spot market-data-only FAQ](https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md)

---

**Acceptance authority:** This document is the binding Gate 3 acceptance contract. Any proposed deviation or change to an approved threshold requires explicit owner approval and a documented revision before implementation or acceptance.


## 14. First implementation slice — current status

The initial implementation is being added under `apps/api/app/market_data/`:

- `models.py`: immutable, decimal-safe Binance Spot price-event models.
- `freshness.py`: locked 3,000 ms fail-closed validation. Source-health and clock-health inputs are explicit; age is calculated using integer microseconds.
- `binance_rest.py`: public `GET /api/v3/trades` latest-trade recovery through `https://data-api.binance.vision`. The trade timestamp is preserved; the timestamp-less ticker-price endpoint is not used as freshness evidence.
- `binance_stream.py`: public `<symbol>@trade` stream through `wss://data-stream.binance.vision`, preserving Binance trade time and event time separately, with protocol ping/pong and bounded reconnect backoff.
- `service.py`: one in-process raw-event cache per symbol, explicit stream start, and on-demand current-price retrieval. Every cache read is revalidated at consumption. A stale/missing stream event triggers one timestamped REST recovery attempt, which must independently pass the same 3-second boundary.

### On-demand integration contract

The request/analysis orchestration boundary now accepts an explicit intent (`educational`, `programming`, `current_market`, or `historical_market`). It calls `BinanceMarketDataService.get_current_price(symbol, clock_healthy=...)` only for `current_market`. Educational and programming requests never call the service. Historical analysis remains a separate path and is not served by this current-price method. The Groq-backed AI intent classifier now supplies this explicit classification. It does not retrieve market data itself; the orchestration boundary remains authoritative.

FastAPI now owns the service through lifespan startup/shutdown, and the owner-only `POST /api/v1/analysis/prepare` endpoint routes explicitly classified requests through `BaymaxRequestOrchestrator`. Educational/programming requests do not fetch market data; historical requests are explicitly marked not implemented; current-market requests require a symbol, a healthy clock provider, and a fresh validated Binance price. The separate Groq-backed analysis generator now consumes these prepared inputs through `POST /api/v1/analysis/respond`. The preparation endpoint remains available for internal diagnostics and does not generate an answer.

### Runtime configuration and owner action

No Binance API key, secret, signature, or private account permission is required or supported. No Binance environment variables need to be added to Render. The public REST and WebSocket hosts are fixed to Binance's market-data-only domains. The backend runtime dependencies now include HTTPX and WebSockets explicitly.

The owner does not need to create a Binance key, change Binance security settings, or add a paid provider for this slice. Deployment/restart should wait until the PR is reviewed and merged; do not deploy this branch directly to production.

### Remaining Gate 3 work

Remaining Gate 3 work includes a production-grade clock-synchronization health provider (the default runtime provider deliberately reports unhealthy, so current-market requests fail closed until one is configured), persistent audit/snapshot records, candle history and gap recovery, order-book synchronization if required, comprehensive WebSocket lifecycle/sequence tests, and the live Binance smoke test. The AI classifier and analysis generator are now implemented, but Gate 3 remains incomplete until the clock-health provider, persistent provenance, historical/candle ingestion, stream recovery tests, and remaining acceptance evidence are delivered.


## 15. Groq-backed AI intelligence integration

The AI layer is implemented as a separate capability from the market-data service:

- `apps/api/app/ai/groq.py`: bounded-timeout asynchronous Groq Chat Completions adapter. The provider boundary is replaceable; the API key is never returned to clients or written to logs.
- `apps/api/app/ai/classifier.py`: strict structured-output intent classifier. It selects only `educational`, `programming`, `current_market`, or `historical_market`, extracts a symbol only when identifiable, and requests clarification for low-confidence or ambiguous messages.
- `apps/api/app/orchestration/requests.py`: remains the only component that decides whether Binance is called. Only `current_market` reaches the current-price service.
- `apps/api/app/ai/generator.py`: produces a structured Markdown answer grounded in the original request and prepared input. It is instructed not to invent missing market values or infer trends/indicators from a single trade.
- `apps/api/app/ai/engine.py`: runs classifier → input orchestration → response generation.
- Owner-only `POST /api/v1/analysis/respond`: natural-language entry point for the full pipeline.

The initial Groq model default is `openai/gpt-oss-20b`, selected because Groq documents strict Structured Outputs support for it. The model can be changed through `GROQ_MODEL` without changing the classifier or generator. Configure `GROQ_API_KEY` and optionally `GROQ_MODEL` on the Render backend only. Do not put the key in Vercel, browser code, or source control. The API can start without a key, but AI responses remain unavailable until one is configured.

The AI layer is analysis-only and has no exchange tools or order execution. It does not make the default clock provider healthy: current-market requests remain blocked until a production-grade clock-health provider is installed. Historical retrieval is still not implemented, and the generator must state that limitation rather than fabricate past market data.


## 16. Production clock-health monitor implementation

The production API now owns a background NTP monitor in its FastAPI lifespan.
It observes the host clock only; it never attempts to change or discipline the
operating-system clock.

- Three independently operated NTP names are queried: Cloudflare, Google, and
  the NTP Pool Project.
- At least two valid responses are required for a health decision.
- Each response must be a valid server-mode NTP response with a synchronized
  leap indicator, stratum 1–15, a matching originate timestamp, and a
  round-trip delay no greater than 1,000 ms.
- The median estimated offset must be within ±500 ms and the observed source
  spread must be no greater than 500 ms.
- Probes run every 30 seconds. A successful health assertion expires after
  90 seconds without a new successful consensus.
- Failed probes, insufficient sources, disagreement, excessive offset, or an
  expired monitor all report unhealthy. The existing orchestrator then blocks
  current-market analysis before price validation or AI generation.
- The monitor is enabled only for `APP_ENV=production`. Development and test
  environments remain fail-closed unless an explicit test provider is injected.

The production runtime must permit outbound DNS and UDP/123 to the configured
NTP sources. If the hosting network blocks NTP, the monitor remains unhealthy;
do not replace it with a constant-true provider or relax the freshness policy.
A live deployment smoke test must verify NTP reachability and the monitor's
reported consensus before current-market analysis can be considered enabled.

The 500 ms clock-offset and 1,000 ms NTP round-trip limits are conservative
monitor implementation thresholds, not changes to the owner-approved
3,000 ms market-price freshness limit. They must not be relaxed without review.
