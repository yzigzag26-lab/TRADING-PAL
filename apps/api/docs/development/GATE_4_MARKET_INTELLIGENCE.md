# Gate 4 — Market Intelligence Engine

**Status:** Implemented in the repository; owner review and acceptance pending.
**Applies to:** Gate 4 of the private, single-owner Baymax system.
**Exchange:** Binance Spot only, public read-only market data.
**Authority:** Analysis and decision *support* only. No order execution,
account access, or trading permission exists anywhere in this gate.

## 1. Purpose

Gate 4 turns a natural-language request such as "Analyse BTCUSDT" or "Should
I buy BTCUSDT?" into an evidence-driven, machine-readable market assessment.
The approved division of responsibility is:

> **Python calculates, Groq reasons and proposes, Python validates, Baymax
> responds.**

The four-stage pipeline:

1. **Python analyses the market (Stage 1).** Verified multi-timeframe
   candles → deterministic indicators, trend, structure, zones, volatility,
   alignment, candidate entry/exit levels, risk/reward and provenance.
   Python is the numerical source of truth.
2. **Groq receives the verified evidence (Stage 2).** Groq gets the compact
   deterministic evidence payload — *without* a Python-selected decision —
   and independently proposes BUY, SELL or WAIT with reasoning.
3. **Python's safety system checks the proposal (Stage 3).** The safety gate
   revalidates market freshness at the release boundary, provenance, clock
   ordering, timeframe completeness, risk constraints and Spot-only
   compatibility. It has absolute veto authority: any unsafe or unsupported
   proposal becomes WAIT.
4. **Final recommendation (Stage 4).** The safety-approved decision is
   returned with the complete structured assessment. On failure, WAIT is
   returned with a clear explanation.

The objective is not a chatbot that describes prices. The objective is a
reliable, maintainable, evidence-driven engine that can honestly answer WAIT.

## 2. Scope and non-goals

- Multi-timeframe technical analysis of Binance Spot candles.
- Deterministic indicator calculation, trend/structure/zone/volatility
  classification, and cross-timeframe alignment.
- Conditional scenario construction for BUY (entry zone, stop-loss,
  take-profit, risk/reward) and exit guidance for SELL, each with explicit
  methodology strings.
- BUY/SELL/WAIT decision support with evidence, risks, invalidation and
  limitations.
- **No** order placement, position sizing, account data, private endpoints,
  leverage, margin, futures, or short exposure. A SELL assessment means
  "exit/reduce an existing spot long" — never a short entry.
- **No** new database tables. Provenance reuses `market_data_snapshots`.

## 3. Architecture

```
app/intelligence/
├── schemas.py        # Typed contracts: IndicatorReading, TrendAssessment,
│                     #   StructureFinding, PriceZone, VolatilityAssessment,
│                     #   TimeframeAnalysis, TimeframeAlignment,
│                     #   MarketIntelligenceReport
├── indicators.py     # Pure-Python indicator engine (no numpy/pandas)
├── trend.py          # Evidence-scored trend classification
├── structure.py      # Confirmed swing detection, HH/HL/LH/LL, BOS/CHoCH,
│                     #   consolidation, breakout/failed breakout
├── zones.py          # Support/resistance zone derivation from swings
├── volatility.py     # ATR%/Bollinger-width level + direction classification
└── analyzer.py       # MarketIntelligenceEngine + MTF alignment

app/market_data/
├── analysis_input.py # MarketIntelligenceInputBuilder + closed_window()
└── decision_safety.py# Gate 3 validators (main): validate_prepared_analysis_inputs,
                      #   validate_market_price_inputs, validate_historical_series_for_decision

app/orchestration/
└── requests.py       # BaymaxRequestOrchestrator (+ allow_trading_decisions flag)

app/strategy/
├── schemas.py        # Scenario, ExitGuidance, StrategyOutcome, SafetyResult
├── setup.py          # Deterministic BUY scenario + SELL exit guidance
└── decision_safety.py# Final fail-closed gate validating the Groq proposal

app/ai/
├── assessment.py     # MarketAssessment + IntelligenceSection contracts,
│                     #   compact evidence context, fallback summary, merge logic
├── engine.py         # Pipeline wiring (Stage 1→4)
└── generator.py      # generate_assessment() — Groq's independent proposal
```

Data flow for `current_market` requests:

```
BaymaxAIEngine.respond
  → BaymaxIntentClassifier (Groq, strict JSON)
  → BaymaxRequestOrchestrator.prepare (validated price + provenance;
    allow_trading_decisions=True only on the intelligence path)
  → MarketIntelligenceInputBuilder.build (5 candle series + provenance)
  → MarketIntelligenceEngine.analyze (per-TF + alignment report)   [Stage 1]
  → evaluate_setup (deterministic candidate: BUY scenario or SELL exit guidance)
  → compact_intelligence_context (verified evidence, NO decided verdict)
  → BaymaxAnalysisGenerator.generate_assessment (Groq proposes BUY/SELL/WAIT)
  → DecisionSafetyGate.evaluate (Gate 3 revalidation at release time + veto)
  → build_market_assessment (validated final MarketAssessment)     [Stage 4]
```

Educational, programming and historical intents never touch the
intelligence pipeline; their Gate 3 behaviour is unchanged. When the
intelligence builder is absent, `validate_prepared_analysis_inputs()` still
enforces the Gate 3 decision block — Gate 4 extends Gate 3, it does not
bypass it.

## 4. Verified input bundle (G4-01)

`MarketIntelligenceInputBuilder` (`app/market_data/analysis_input.py`)
consumes the `PreparedAnalysisInput` produced by the existing orchestrator —
it never fetches the price itself. For each timeframe it:

- Computes a closed-candle window via `closed_window()`: the range ends at the
  open boundary of the last *fully closed* candle, so the currently forming
  candle is never requested as analysis input.
- Calls the existing `BinanceHistoricalCandleService.fetch()`, inheriting all
  Gate 3 validation: OHLC integrity, interval alignment, continuity, bounded
  pagination, and gap recovery.
- Records every series through `MarketDataProvenanceRepository.
  record_historical_series()` and stamps the returned snapshot ID onto the
  series and the per-timeframe analysis.
- Fetches all five timeframes concurrently (`asyncio.gather`). A single
  timeframe failure degrades the report rather than aborting it; the safety
  gate decides whether the remaining evidence is still defensible.
- Fails closed (`MarketIntelligenceInputUnavailable` → HTTP 503) when the
  verified price or its provenance snapshot is missing, or when provenance
  persistence fails.

### Timeframes and candle budget

`ANALYSIS_TIMEFRAMES = ("5m", "15m", "1h", "4h", "1d")` with
`CANDLES_PER_TIMEFRAME = 300` — comfortably above the longest warm-up
(ADX ≈ 30 candles, MACD ≈ 35) and swing-confirmation needs, while staying
within Binance's 1,000-candle page limit (one page per timeframe).

## 5. Deterministic indicators (G4-02)

All indicators are hand-rolled pure Python in `app/intelligence/indicators.py`.
No numpy/pandas dependency was added. Calculations use binary floating point
(the standard convention for technical indicators); prices enter as exact
`Decimal` values converted once to `float`, and outputs are rounded to 10
significant decimals. This is documented as a calculation convenience, not
decimal-exact arithmetic.

| Indicator | Parameters | Warm-up | Notes |
|---|---|---|---|
| SMA | 20, 50 | period | First value at index period−1 |
| EMA | 20, 50 | period | SMA-seeded; seed is documented |
| RSI | 14 | 15 closes | Wilder smoothing; flat series (avg gain = avg loss = 0) reports neutral **50** |
| MACD | 12/26/9 | ~35 | Line, signal, histogram |
| ATR | 14 | 15 candles | Wilder smoothing of true range |
| Bollinger | 20, ±2σ | 20 | Upper/middle/lower/width/width-percentile/%B |
| ADX | 14 | ~30 | Wilder +DI/−DI/ADX |
| Volume | SMA 20 | 20 | Relative volume vs SMA |

Every `IndicatorReading` carries `candle_count`, `warmup_candles`,
`sufficient_history`, `latest_input_open_time` and `calculated_at`. When
history is insufficient the reading reports `values={}` — indicators never
emit partial or guessed numbers. Division-by-zero paths are guarded: RSI on
a flat series is 50 (not 100), ATR/percentiles on degenerate ranges return
`None`, and all outputs are finite.

## 6. Per-timeframe analysis

`MarketIntelligenceEngine._analyze_timeframe` filters the series to
`is_closed` candles only (forming candles are excluded and counted in
limitations), then computes:

- **Trend** (`trend.py`): weighted evidence vote across close-vs-EMA20,
  EMA20-vs-EMA50, SMA20-vs-SMA50, RSI(14) momentum, MACD histogram, ADX
  directional movement, and 20-candle price slope. Score ∈ [−1, 1];
  thresholds ±0.35 classify bullish/bearish, with `ranging`/`transitioning`/
  `uncertain` fallbacks. ADX < 20 suppresses conviction (score × 0.6).
  **Equal moving averages cast a neutral vote** — fast = slow is never
  counted as bearish.
- **Structure** (`structure.py`): swing highs/lows confirmed only after
  `swing_window` (3) subsequent closed candles — no look-ahead. Consecutive
  same-type swings classify HH/HL/LH/LL; closes beyond the latest confirmed
  swing extreme produce BOS (with-trend) or CHoCH (against-trend);
  consolidation is detected when the last 20 candles stay inside
  2×ATR of price; breakout/failed-breakout compare the last close to the
  prior 20-candle extreme.
- **Zones** (`zones.py`): confirmed swing extremes are clustered within a
  tolerance of `max(0.1% of price, 0.5×ATR)`. Each zone records side,
  bounds, touches, strength (saturated at 5 touches), active flag and source
  candle times. A zone is invalidated when a later closed candle closes
  through it by more than `0.25×ATR`.
- **Volatility** (`volatility.py`): level from the mean percentile rank of
  ATR% and Bollinger width against their own trailing history
  (≤0.35 low, ≥0.65 high); direction from the ATR% ratio over 14 candles
  (≥1.15 expanding, ≤0.87 contracting), with Bollinger width as secondary
  confirmation.

A timeframe is `usable` only with ≥ `MIN_USABLE_CANDLES` (60) closed candles;
otherwise its analysis still reports indicators but structure/zones are
skipped and limitations are recorded.

## 7. Multi-timeframe alignment

`MarketIntelligenceEngine._align` requires ≥ `MIN_ALIGNMENT_TIMEFRAMES` (3)
usable timeframes, else status `insufficient`. Statuses:

- `aligned_bullish` / `aligned_bearish` — every usable timeframe agrees.
- `partial` — directional majority without full agreement.
- `conflicting` — bullish and bearish timeframes both present, or no
  coherent bias.
- `insufficient` — too few usable timeframes.

Higher-timeframe (4h, 1d) vs lower-timeframe disagreement is recorded as an
alignment note for the model and the owner.

## 8. Deterministic candidate construction (`setup_zone_atr_v1`, `spot_exit_zone_v1`)

`evaluate_setup` (`app/strategy/setup.py`) builds a *candidate* — never the
final decision:

- `aligned_bullish` → BUY candidate; `aligned_bearish` → SELL candidate;
  anything else → WAIT.
- Setup timeframe preference: `1h`, then `15m`, `4h`, `5m`, `1d` (first
  usable).
- **Volatility gate:** `high` + `expanding` volatility on the setup
  timeframe → WAIT (hard block).

### BUY candidate (`Scenario`)

- **Entry zone:** the active support zone containing the current price,
  else a ±`0.10×ATR` band around the validated price.
- **Stop-loss:** below the protective support zone minus `0.25×ATR` buffer.
- **Take-profit 1:** near boundary of the nearest resistance zone; TP2 from
  the next one when present.
- **Hard requirements:** protective zone exists, target zone exists, risk
  and reward distances positive, and reward/risk ≥ `MIN_RISK_REWARD` (1.5).
  Any failure → WAIT. Levels are never manufactured to force a
  recommendation.

### SELL candidate (`ExitGuidance`) — Spot-only semantics

Binance Spot V1 has no short, margin or futures capability, so SELL is
**exit/reduction guidance for an existing long holding** — never a
short-entry scenario:

- `kind: "spot_exit"`, `decision: "SELL"`.
- `trim_levels`: nearest resistance zones *above* price (sell into
  remaining strength).
- `breakdown_exit`: nearest support zone *below* price — the level whose
  loss on a closed candle argues for full exit.
- `hold_invalidation`: what would weaken the bearish exit thesis.
- `note`: explicitly states this is not a short entry and that Baymax does
  not know whether the user holds the asset.
- No entry zone, stop-loss or take-profit short structure is produced.
  If no verified zone exists to anchor the guidance → WAIT.

## 9. Groq's independent proposal (Stage 2)

`compact_intelligence_context()` serialises only verified deterministic
values into the Groq prompt: per-timeframe trend/structure/volatility/
indicators/zones, alignment, data quality, readiness, candidate levels
(labeled `candidate_levels`, never "the decision"), and strategy evidence
reasons/blocking reasons. The payload deliberately contains **no**
Python-selected verdict — Groq must reason independently.

`generate_assessment()` asks Groq to propose exactly one of BUY / SELL /
WAIT, explain its reasoning from the supplied evidence, and respect the
Spot-only SELL semantics. Output is constrained by
`ASSESSMENT_RESPONSE_SCHEMA` (strict JSON schema) and validated by
`_AssessmentDraft`. Invalid JSON, missing fields, unsupported decisions and
provider failures all raise `AnalysisGenerationError` → the engine proceeds
with `proposal=None` → deterministic WAIT.

## 10. Decision-safety gate — Python validates Groq (Stage 3)

`DecisionSafetyGate.evaluate(report, candidate, proposal, …)` runs at the
**release boundary** — after candle retrieval, indicator calculation and
Groq latency — so freshness is recomputed against the current clock, not
the original validation timestamp.

### Gate 3 integration (shared boundary)

The gate calls `validate_market_price_inputs()` from
`app/market_data/decision_safety.py` (Gate 3, `main`) inside the release
check. This preserves every Gate 3 guarantee:

- Required market evidence present and `ready`.
- Persisted market-snapshot provenance ID.
- Request symbol ↔ price symbol identity.
- BINANCE/SPOT exchange-market identity and trusted source
  (`binance_spot_websocket` / `binance_spot_rest`).
- Decimal market `event_id`.
- Timestamp ordering `market ≤ received ≤ validated ≤ now` (plus optional
  exchange-timestamp ordering); naive/future/contradictory timestamps fail.
- Recorded `age_ms_at_validation` must equal the timestamp-derived age.
- **Age recomputed at release:** `now − market_event_timestamp` must be
  within [0, 3,000 ms]. The original market-event timestamp is never
  replaced by a processing timestamp; invalid clocks fail closed.

`validate_prepared_analysis_inputs()` (which additionally enforces the
intent gates and the Gate 3 decision-request block) remains the boundary
for the non-intelligence path. Gate 4 lifts the decision block *only* when
the complete candle-series + strategy evidence exists — the exact gap the
Gate 3 block was waiting for.

### Report and candidate checks

- All five expected timeframes (`5m, 15m, 1h, 4h, 1d`) present; ≥3 analyses,
  ≥2 usable; each series complete, ≥60 candles, valid close, no unresolved
  limitations; per-timeframe provenance when `require_provenance` is set.
- Alignment must not be `conflicting`; data quality not `insufficient`;
  readiness not `blocked`; no missing inputs.
- Candidate blocking reasons propagate; a BUY/SELL candidate must carry its
  payload; scenario risk/reward ≥ 1.5 and positive price levels.

### Proposal resolution (`_resolve_proposal`)

| Groq proposal | Safety state | Final decision |
|---|---|---|
| `None` (provider/validation failure) | any | WAIT |
| `WAIT` | any | WAIT |
| `BUY`/`SELL` | any block reason | WAIT (veto) |
| `BUY`/`SELL` | clean, matches deterministic candidate | BUY/SELL |
| `BUY`/`SELL` | clean, contradicts candidate | WAIT (mismatch) |

`SafetyResult.model_proposal` records Groq's original proposal for audit;
`checks` records which rule fired (`model_proposal_confirmed_by_evidence`,
`model_proposal_vetoed_by_safety`, `model_proposal_mismatch`,
`model_proposal_unavailable`).

## 11. Complete assessment contract (F6)

`MarketAssessment` is the machine-readable result:

```json
{
  "decision": "BUY | SELL | WAIT",
  "summary": "Markdown explanation (Groq text only when its proposal was accepted)",
  "key_evidence": ["..."], "risks": ["..."],
  "invalidation_conditions": ["..."], "limitations": ["..."],
  "timeframe_alignment": "aligned_bullish",
  "data_quality": "complete",
  "scenario": { "..." } | null,
  "exit_guidance": { "kind": "spot_exit", "note": "...",
                     "trim_levels": [...], "breakdown_exit": {...},
                     "hold_invalidation": "...", "methodology": "..." } | null,
  "model_decision": "BUY | SELL | WAIT | null",
  "intelligence": {
    "symbol": "BTCUSDT", "exchange": "BINANCE", "market": "SPOT",
    "analyzed_at": "...", "current_price": "...",
    "price_provenance_id": "...",
    "alignment_status": "...", "alignment_directions": {...},
    "data_quality": "...", "readiness": "...",
    "missing_inputs": [...], "limitations": [...],
    "timeframes": [{
      "interval": "1h", "usable": true,
      "candle_count": 300, "closed_candle_count": 300,
      "series_complete": true, "snapshot_id": "...",
      "last_closed_close": "...",
      "trend_direction": "bullish", "trend_score": 0.62,
      "trend_evidence": [...], "structure_kinds": [...],
      "structure_details": [...], "zones": [{"side":"support", ...}],
      "volatility_level": "normal", "volatility_direction": "stable",
      "atr": 1.2, "atr_percent": 1.4,
      "bollinger_width_percentile": 55.0,
      "indicators": [{"name":"RSI","parameters":{"period":14},
                      "values":{"value":55.1},"sufficient_history":true}],
      "limitations": []
    }]
  }
}
```

- `decision` always comes from the safety gate — never from model text.
- `model_decision` preserves Groq's proposal for audit (e.g., a vetoed BUY).
- `intelligence.timeframes` exposes all five intervals with per-timeframe
  indicators, zones, structure and provenance; unavailable values are
  `null`/empty with `limitations` explaining why — nothing is fabricated.
- `build_market_assessment()` uses Groq's summary/evidence/risks only when
  `model_decision == decision`; otherwise the deterministic fallback summary
  is used and the limitation notes the veto.
- `deterministic_fallback_summary()` contains only verified facts.

## 12. API contract

`POST /api/v1/analysis/respond` (owner session):

- Request unchanged: `{"message": "..."}`.
- Response adds `assessment: MarketAssessment | null` (now including
  `exit_guidance`, `model_decision`, `intelligence`). All Gate 3 fields are
  preserved; `answer` carries the assessment summary for market requests.
- The orchestrator is constructed with `allow_trading_decisions=True` on this
  endpoint so decision requests retrieve verified price evidence; without
  the intelligence path the Gate 3 decision block still applies.
- Failures remain generic: 401 unauthenticated, 503 when verified market
  data, provenance, or the AI provider is unavailable, 422 on invalid
  requests. Provider and internal details are never leaked.

`POST /api/v1/analysis/prepare`, `POST /api/v1/analysis/history`, auth and
diagnostics endpoints are unchanged.

## 13. Frontend integration

`apps/web/src/app/page.tsx` — the analysis workspace posts to
`/api/v1/analysis/respond` through the same-origin `/api` proxy.

- `AssessmentCard` renders: verdict badge (**BUY** green, **SELL** red,
  **WAIT** white-on-dark), alignment/data-quality tags, a "model proposed X —
  vetoed" tag when Groq was overruled, the Markdown summary, the BUY
  scenario levels or the SELL spot-exit guidance block, a per-timeframe
  intelligence table (trend, score, volatility, last close, usability) with
  expandable per-timeframe details (candles, structure, indicator readings,
  zones, limitations), key evidence, risks, invalidation conditions,
  limitations, and an "analysis only" footnote.
- A pending state is shown while the request runs; send is disabled during
  flight.
- 401 responses prompt re-authentication; other failures render an honest
  unavailable message — no fabricated analysis.
- Chart image attachments remain client-side only; the backend contract is
  text-only (documented limitation).

## 14. Security and fail-closed behaviour

- No Binance credentials, private endpoints, order endpoints, or trading
  code were added.
- User messages remain untrusted input: JSON-encoded into prompts with
  explicit system rules; the model cannot fetch data or override the
  deterministic decision.
- Every consumed series and the price snapshot are provenance-recorded in
  the append-only `market_data_snapshots` table.
- Stale, missing, incomplete, contradictory, or unverifiable evidence always
  resolves to WAIT — including staleness introduced *during* analysis
  (release-time revalidation), not only at initial validation.
- Groq cannot fabricate market evidence, alter verified numbers, or force a
  recommendation: its proposal is schema-validated and safety-gated.
- No new environment variables were required; all periods, thresholds and
  timeframes are versioned constants in the modules above.

## 15. Testing

Deterministic unit tests (no live network) cover:

- `tests/test_intelligence_indicators.py` — known-value vectors, warm-up/
  insufficient-history, empty series, **flat-series RSI = 50**, RSI 100/0
  extremes.
- `tests/test_intelligence_analysis.py` — swing confirmation, structure,
  zones, trend classification incl. **equal-MA neutrality** and flat-series
  neutrality, volatility classes, MTF reports.
- `tests/test_intelligence_input.py` — five-timeframe bundle assembly,
  degradation, provenance, closed-window alignment, fail-closed inputs.
- `tests/test_strategy.py` — BUY scenario math, R:R gating, volatility
  block, **SELL exit-guidance semantics (no short scenario)**, and every
  safety-gate path: release-time stale price, fresh-at-release, conflicting
  alignment, unavailable proposal, proposal/candidate mismatch, symbol
  mismatch, non-decimal event ID, missing provenance, incomplete series,
  missing timeframes.
- `tests/test_gate4_engine.py` — end-to-end engine flow with fakes:
  Groq BUY/SELL/WAIT proposals, safety veto of an unsafe BUY, provider
  failure fallback, **release-time freshness veto**, and the Gate 3
  decision block preserved when decision evidence is absent.
- `tests/test_decision_safety.py`, `tests/test_analysis_orchestration.py`,
  `tests/test_ai_engine.py` — Gate 3 regression coverage.

**Verification status at handover:** `ruff format --check app tests`,
`ruff check app tests` and `mypy app tests` (strict, 94 files) pass; the
full `pytest` suite passes (253 tests). Frontend `npm run lint` (0 errors,
pre-existing warnings) and `npm run typecheck` pass. `npm run build` could
not complete on the authoring machine (Next.js SWC binary download kept
failing) and `zensical build --strict` was not run (tool not installed
locally) — both must be verified in CI/owner environment before merge.

## 16. Known limitations

- VWAP is not computed (no session-anchor convention defined).
- Chart-image analysis is not implemented; attachments are display-only.
- Natural-language `historical_market` intent still returns
  `historical_not_implemented` in the respond pipeline (the structured
  `/analysis/history` endpoint is unaffected).
- Scenario levels are zone/ATR-derived approximations, not order-book or
  liquidity-aware levels.
- The 300-candle window may miss very-long-horizon structure on 1d.
- Indicator math is float-based (documented); price levels in scenarios use
  `Decimal` end-to-end.
- SELL guidance describes levels for an existing holding; Baymax has no
  position data, so it cannot know whether the user actually holds the
  asset — this is stated in every SELL response.
- Groq interpretation is advisory prose over deterministic facts; if the
  provider is unavailable or its proposal is unsafe, the deterministic
  fallback/WAIT result is shown.

## 17. Handover checklist

- [x] Full `pytest` suite green (253 tests, Gate 1–4).
- [x] `ruff format --check app tests`, `ruff check app tests`,
      `mypy app tests` green locally.
- [ ] `npm run lint`, `npm run typecheck`, `npm run build` green for
      `apps/web` — lint/typecheck pass locally; **build not verified**
      (SWC download failure on authoring machine; verify in CI).
- [ ] `zensical build --strict` green — **not run locally** (tool not
      installed); verify in CI.
- [ ] Owner review of decision thresholds (R:R ≥ 1.5, volatility gate,
      swing window, zone tolerance) before production reliance.
- [ ] No production deployment or merge without explicit owner approval.
