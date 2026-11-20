# Gate 4 — Market Intelligence Engine

**Status:** Implemented in the repository; owner review and acceptance pending.
**Applies to:** Gate 4 of the private, single-owner Baymax system.
**Exchange:** Binance Spot only, public read-only market data.
**Authority:** Analysis and decision *support* only. No order execution,
account access, or trading permission exists anywhere in this gate.

## 1. Purpose

Gate 4 turns a natural-language request such as "Analyse BTCUSDT" into an
evidence-driven, machine-readable market assessment. The pipeline:

1. Classifies the request (existing Gate 3 Groq intent classifier).
2. Prepares verified inputs: one fresh `ValidatedPrice` (3,000 ms policy) plus
   one validated, closed-candle `HistoricalCandleSeries` per analysis
   timeframe.
3. Computes deterministic indicators and analytical findings in pure Python.
4. Derives a deterministic BUY/SELL/WAIT proposal with entry/stop/target
   levels only when the evidence justifies them.
5. Applies a final fail-closed safety gate.
6. Asks Groq to *interpret* the verified evidence in a strict JSON schema;
   Python enforces the deterministic decision and discards disagreeing model
   output.
7. Returns a structured `assessment` object that the frontend renders as a
   colour-coded verdict card.

The objective is not a chatbot that describes prices. The objective is a
reliable, maintainable, evidence-driven engine that can honestly answer WAIT.

## 2. Scope and non-goals

- Multi-timeframe technical analysis of Binance Spot candles.
- Deterministic indicator calculation, trend/structure/zone/volatility
  classification, and cross-timeframe alignment.
- Conditional scenario construction (entry zone, stop-loss, take-profit,
  risk/reward) with explicit methodology strings.
- BUY/SELL/WAIT decision support with evidence, risks, invalidation and
  limitations.
- **No** order placement, position sizing, account data, private endpoints,
  leverage, or short exposure. A SELL assessment means "exit/reduce" on
  spot, never a leveraged short.
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
└── analysis_input.py # MarketIntelligenceInputBuilder + closed_window()

app/strategy/
├── schemas.py        # Scenario, StrategyOutcome, SafetyResult
├── setup.py          # Deterministic scenario construction (setup_zone_atr_v1)
└── decision_safety.py# Final fail-closed gate

app/ai/
├── assessment.py     # MarketAssessment contract, compact evidence context,
│                     #   deterministic fallback summary, JSON schema
├── engine.py         # Pipeline wiring
└── generator.py      # generate_assessment() — structured Groq output
```

Data flow for `current_market` requests:

```
BaymaxAIEngine.respond
  → BaymaxIntentClassifier (Groq, strict JSON)
  → BaymaxRequestOrchestrator.prepare (validated price + provenance)
  → MarketIntelligenceInputBuilder.build (5 candle series + provenance)
  → MarketIntelligenceEngine.analyze (per-TF + alignment report)
  → evaluate_setup (deterministic scenario proposal)
  → DecisionSafetyGate.evaluate (fail-closed override to WAIT)
  → BaymaxAnalysisGenerator.generate_assessment (Groq JSON interpretation)
  → MarketAssessment (decision forced to safety result)
```

Educational, programming and historical intents never touch the
intelligence pipeline; their Gate 3 behaviour is unchanged.

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
| RSI | 14 | 15 closes | Wilder smoothing |
| MACD | 12/26/9 | ~35 | Line, signal, histogram |
| ATR | 14 | 15 candles | Wilder smoothing of true range |
| Bollinger | 20, ±2σ | 20 | Upper/middle/lower/width/width-percentile/%B |
| ADX | 14 | ~30 | Wilder +DI/−DI/ADX |
| Volume | SMA 20 | 20 | Relative volume vs SMA |

Every `IndicatorReading` carries `candle_count`, `warmup_candles`,
`sufficient_history`, `latest_input_open_time` and `calculated_at`. When
history is insufficient the reading reports `values={}` — indicators never
emit partial or guessed numbers.

## 6. Per-timeframe analysis

`MarketIntelligenceEngine._analyze_timeframe` filters the series to
`is_closed` candles only (forming candles are excluded and counted in
limitations), then computes:

- **Trend** (`trend.py`): weighted evidence vote across close-vs-EMA20,
  EMA20-vs-EMA50, SMA20-vs-SMA50, RSI(14) momentum, MACD histogram, ADX
  directional movement, and 20-candle price slope. Score ∈ [−1, 1];
  thresholds ±0.35 classify bullish/bearish, with `ranging`/`transitioning`/
  `uncertain` fallbacks. ADX < 20 suppresses conviction (score × 0.6).
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

## 8. Deterministic scenario construction (`setup_zone_atr_v1`)

`evaluate_setup` (`app/strategy/setup.py`) proposes a decision only from
verified evidence:

- `aligned_bullish` → BUY candidate; `aligned_bearish` → SELL candidate
  (exit/reduction assessment); anything else → WAIT.
- Setup timeframe preference: `1h`, then `15m`, `4h`, `5m`, `1d` (first
  usable).
- **Volatility gate:** `high` + `expanding` volatility on the setup
  timeframe → WAIT (hard block).
- **Entry zone:** the active protective-side zone containing the current
  price, else a ±`0.10×ATR` band around the validated price.
- **Stop-loss:** beyond the far side of the protective zone minus
  `0.25×ATR` buffer.
- **Take-profit 1:** near boundary of the nearest opposing active zone;
  TP2 from the next opposing zone when present.
- **Hard requirements:** protective zone exists, target zone exists, risk
  and reward distances positive, and reward/risk ≥ `MIN_RISK_REWARD` (1.5).
  Any failure → WAIT. Levels are never manufactured to force a
  recommendation.

## 9. Decision-safety gate (fail-closed)

`DecisionSafetyGate.evaluate` re-verifies every mandatory condition
immediately before release and forces WAIT on any failure:

- Symbol identity across price and all analysed timeframes.
- Current-price freshness ≤ 3,000 ms (`MAX_PRICE_AGE_MS`, Gate 3 policy).
- Price symbol matches the analysis symbol.
- All five required timeframe analyses present, each series complete and
  usable.
- When `require_provenance` is set (production): every timeframe analysis
  and the price must carry snapshot provenance IDs.
- Timeframe alignment must not be `insufficient`.
- A directional proposal must have a deterministic scenario.

The gate returns `SafetyResult` with the final decision, scenario (only when
not WAIT), block reasons and the list of checks performed — all of which are
surfaced in the API response evidence.

## 10. Structured AI interpretation

`MarketAssessment` (`app/ai/assessment.py`) is the machine-readable contract:

```json
{
  "decision": "BUY | SELL | WAIT",
  "summary": "Markdown explanation",
  "key_evidence": ["..."],
  "risks": ["..."],
  "invalidation_conditions": ["..."],
  "limitations": ["..."],
  "timeframe_alignment": "aligned_bullish",
  "data_quality": "complete",
  "scenario": { "decision": "...", "entry_zone": {...}, "stop_loss": "...",
                "take_profit_1": "...", "take_profit_2": "...",
                "risk_reward_ratio": "1.82", "invalidation": "...",
                "methodology": "setup_zone_atr_v1" }
}
```

- `compact_intelligence_context()` serialises only verified deterministic
  values (indicator readings, trend, structure kinds, zones, volatility,
  alignment, the deterministic scenario, and safety checks) into the Groq
  prompt. Raw candle dumps are never sent.
- Groq answers through a strict JSON-schema response format
  (`ASSESSMENT_RESPONSE_SCHEMA`), validated by `_AssessmentDraft` and
  `MarketAssessment` (extra fields forbidden).
- The model's `decision` must equal the safety-gated decision. On any
  disagreement — or on provider/validation failure — the deterministic
  summary (`deterministic_fallback_summary`) is returned instead, built only
  from verified facts.
- Scenario numbers in the response always come from the deterministic
  `Scenario`; the model can explain but never supply or alter them.

## 11. API contract

`POST /api/v1/analysis/respond` (owner session) is extended additively:

- Request unchanged: `{"message": "..."}`.
- Response adds `assessment: MarketAssessment | null`. All Gate 3 fields
  (`answer`, `intent`, `symbol`, `market_data_status`,
  `needs_clarification`, `market_snapshot_id`) are preserved; `answer` now
  carries the assessment summary for market requests.
- Failures remain generic: 401 unauthenticated, 503 when verified market
  data, provenance, or the AI provider is unavailable, 422 on invalid
  requests. Provider and internal details are never leaked.

`POST /api/v1/analysis/prepare`, `POST /api/v1/analysis/history`, auth and
diagnostics endpoints are unchanged.

## 12. Frontend integration

`apps/web/src/app/page.tsx` — the Chart analysis workspace now posts to
`/api/v1/analysis/respond` through the existing same-origin `/api` proxy.

- Assistant messages render an `AssessmentCard`: a verdict badge
  (**BUY** green, **SELL** red, **WAIT** white-on-dark), the Markdown
  summary, the deterministic scenario levels (entry zone, stop-loss,
  take-profits, risk/reward, invalidation), key evidence, risks,
  invalidation conditions, limitations, and an "analysis only" footnote.
- A pending state ("Analysing verified market data…") is shown while the
  request runs; send is disabled during flight.
- 401 responses prompt re-authentication; other failures render an honest
  unavailable message — no fabricated analysis.
- Chart image attachments remain client-side only; the backend contract is
  text-only (documented limitation).

## 13. Security and fail-closed behaviour

- No Binance credentials, private endpoints, order endpoints, or trading
  code were added.
- User messages remain untrusted input: JSON-encoded into prompts with
  explicit system rules; the model cannot fetch data or override the
  deterministic decision.
- Every consumed series and the price snapshot are provenance-recorded in
  the append-only `market_data_snapshots` table.
- Stale, missing, incomplete, contradictory, or unverifiable evidence always
  resolves to WAIT — the system explains why rather than guessing.
- No new environment variables were required; all periods, thresholds and
  timeframes are versioned constants in the modules above.

## 14. Testing

Deterministic unit tests (no live network) cover:

- `tests/test_intelligence_indicators.py` — known-value vectors (SMA, EMA,
  RSI 100/0 extremes, MACD histogram sign, constant-range ATR, Bollinger
  ordering, ADX on trending series), warm-up/insufficient-history behaviour,
  empty series.
- `tests/test_intelligence_analysis.py` — swing confirmation, structure
  findings, zone derivation/invalidation, trend classification on
  up/down/range fixtures, volatility classes, full/partial/conflicting
  multi-timeframe reports.
- `tests/test_intelligence_input.py` — five-timeframe bundle assembly,
  per-timeframe degradation, provenance recording, closed-window alignment,
  fail-closed input errors.
- `tests/test_strategy.py` — BUY/SELL scenario level math, R:R gating,
  volatility block, and every safety-gate rejection path (stale price,
  incomplete series, missing timeframe, missing provenance).

**Verification status at handover:** `ruff format --check`, `ruff check`
and `mypy app tests` (strict) pass; the new Gate 4 test files pass (44
tests). The full `pytest` suite, frontend `npm run lint`/`typecheck`/`build`
and the Zensical docs build were **not** run to completion before handover
and must be verified before merge.

## 15. Known limitations

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
- Groq interpretation is advisory prose over deterministic facts; if the
  provider is unavailable the deterministic fallback summary is shown.

## 16. Handover checklist

- [ ] Full `pytest` suite green (Gate 1–4).
- [ ] `ruff format --check app tests`, `ruff check app tests`,
      `mypy app tests` green in CI.
- [ ] `npm run lint`, `npm run typecheck`, `npm run build` green for
      `apps/web`.
- [ ] `zensical build --strict` green for both doc trees.
- [ ] Owner review of decision thresholds (R:R ≥ 1.5, volatility gate,
      swing window, zone tolerance) before production reliance.
- [ ] No production deployment or merge without explicit owner approval.
