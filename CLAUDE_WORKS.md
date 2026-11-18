# Baymax Backend — Claude Code Work Order

**Repository:** `yzigzag26-lab/TRADING-PAL`  
**Product:** Baymax (the product is still named Trading Pal in the repository)  
**Frontend:** https://baymax-nu.vercel.app  
**Backend target:** Python + FastAPI on Render  
**Database/Auth/Storage:** Supabase  
**Status:** Work allocation and integration catalogue; not a deployment authorization.

## 1. Purpose and authority

**Current implementation clarification (2026-11-16):** This work-order contains original Phase 1 planning text. For implemented behaviour, follow the current repository README and `apps/api/README.md`: Baymax uses a private single-owner Argon2id password and signed `HttpOnly` session, with Supabase PostgreSQL for persistence; it does not currently use Supabase Auth/JWT login. The current API explorer is Swagger UI at `/docs` with generated `/openapi.json`, and ReDoc is disabled. The original Scalar/Supabase Auth planning language below is historical unless explicitly re-approved. Gate 3's Binance scope and acceptance rules are controlled by `docs/development/GATE_3_MARKET_DATA.md`. Gate 3 implementation is now merged; production NTP/REST/basic WebSocket diagnostics and one durable snapshot commit with independent Supabase readback passed on 2026-11-18. Gate 3 remains incomplete, with full deployed-service WebSocket lifecycle recovery (G3-05) the next production acceptance item. See Section 19 of the Gate 3 contract for the evidence record.

This file defines the exact work split between Claude Code and ChatGPT for the Baymax backend.

The existing `docs/IMPLEMENTATION_HANDOFF.md` remains the controlling Phase 1 scope document. This file supplements it by assigning responsibilities. If documents conflict, stop and ask the owner; do not silently choose one.

### Decision ownership

- **ChatGPT is the solution architect and owner of the core backend architecture, security model, API contracts, database design, integrations, final integration, review and deployment readiness.**
- **Claude Code is the first implementation contributor. Claude handles bounded supporting work that does not determine or alter core architecture.**
- The project owner approves scope changes, external service provisioning, paid services, secrets access, production configuration and final release.

Claude must not treat its ability to edit a file as permission to make an architectural decision.

## 2. Product and scope guardrails

Baymax Version 1 is a cryptocurrency trading-intelligence assistant. It will interpret chart uploads, verify observations against exchange data, calculate indicators deterministically, synthesize evidence and produce conditional scenarios with uncertainty and invalidation.

Version 1 does **not** place orders, execute trades, manage funds, or promise profits.

The current Phase 1 foundation remains narrower: backend foundation, Supabase Auth/PostgreSQL, secure user-scoped APIs, documentation, tests, CI and deployment readiness. AI inference, chart analysis and market-data features are later implementation stages and must not be slipped into the foundation milestone.

Non-negotiable:
1. No fabricated prices, balances, signals, users, chart analyses or history.
2. Gate 3 uses Binance Spot public market-data-only REST and WebSocket interfaces. Public Spot market-data endpoints with security type `NONE` require no API key, secret, signature, or account permission. Do not create or configure Binance credentials for Gate 3. Do not call private account, user-data, trading, transfer, margin, futures, or withdrawal endpoints. The binding Gate 3 requirements are in `docs/development/GATE_3_MARKET_DATA.md`.
3. No live trading, order endpoints or withdrawal permissions.
4. No paid service, plan upgrade or usage-based resource without explicit owner approval.
5. Never commit secrets or expose privileged keys in browser code, logs, prompts, docs or CI output.
6. Do not add microservices, queues, Redis, Kubernetes or agent frameworks without an approved requirement.
7. Keep the existing frontend interface intact unless the owner asks for a specific change.
8. Work on a feature branch; do not push directly to `main`, force-push shared history, or merge your own PR unless specifically authorized.

## 3. Work sequence

The required sequence is:

1. After the owner approves this work order and explicitly authorizes the supporting-work start, Claude completes the bounded supporting work in Section 4 on a dedicated branch and opens a pull request.
2. Claude provides the handoff report in Section 5.
3. ChatGPT inspects the complete diff, checks it against the implementation handoff, runs/reviews verification evidence and requests corrections where needed.
4. ChatGPT then owns and implements the core backend architecture and required integration work in a separate, clearly scoped change set.
5. ChatGPT performs end-to-end review, security checks, documentation/API consistency checks and deployment-readiness verification.
6. The owner approves the deployment action. No agent may provision or deploy production services without the required owner authorization.

Do not start ChatGPT's core implementation while Claude is still changing the same working tree or shared files. Use separate branches and merge/rebase in a controlled order.

## 4. Claude Code — first implementation assignment

### Claude owns

A. **Backend documentation foundation**
- Create or improve backend-specific developer documentation.
- Draft local setup, test, environment-variable and deployment-operation instructions using placeholders only.
- Create an architecture-document skeleton that links to the approved handoff, but do not make new architecture decisions.
- Document the API documentation workflow: FastAPI-generated OpenAPI is authoritative; Scalar is the interactive reference; Zensical is the human-readable engineering documentation.
- Record unresolved decisions instead of guessing.

B. **Python quality-tooling foundation**
- Configure Python formatting/linting, static type checking and test tooling for approved Python 3.12.
- Preferred candidates: Ruff for lint/format and pytest for tests; propose the type checker and explain its trade-offs before locking it in.
- Keep tool configuration small and compatible with the chosen Python runtime.
- Use the owner-approved Python 3.12 runtime and the standard venv + pip workflow. Do not change either without owner approval.

C. **Test infrastructure scaffolding**
- Establish pytest configuration and a minimal test layout/fixtures.
- Add only tests for tooling/configuration scaffolding or documentation build checks that can be meaningfully verified without a real Supabase project.
- Do not create fake business behaviour or tests that pass by mocking away all meaningful logic.
- Do not create fake database credentials or require production secrets to run local tests.

D. **Documentation build**
- Add Zensical configuration and navigation for existing/approved documentation.
- Ensure docs build locally and in CI.
- Keep the docs hosting destination undecided until account/plan eligibility is checked and approved.

E. **CI preparation**
- Add or extend GitHub Actions for documentation build and safe Python static checks.
- Do not add deployment workflows, publish artifacts publicly, or configure production secrets.
- CI must not print environment values or credentials.

F. **Backend package metadata**
- Prepare minimal backend project metadata for approved Python 3.12 using pip-compatible PEP 621 metadata.
- Avoid adding speculative runtime dependencies for AI, market data, databases or indicator calculations before the corresponding implementation phase.
- Pin/lock dependencies reproducibly once the package manager and runtime are agreed.

### Claude must NOT own or modify

Unless ChatGPT explicitly delegates a specific file later, Claude must not implement or change:

- Core FastAPI application lifecycle or `main.py`.
- Core API router/version registration or endpoint behaviour.
- Authentication, Supabase JWT signature verification, JWKS/key rotation or authorization.
- Database connection/session design, repositories, ORM models, SQL migrations or RLS policies.
- Core Pydantic request/response contracts and shared error envelope.
- CORS/security middleware behaviour.
- Market-data ingestion, exchange adapters, caching or normalization.
- AI provider clients, model selection, prompts, vision processing or orchestration.
- Risk engine, deterministic indicators, analysis specialists or trading logic.
- Production deployment configuration, cloud resources, secret stores or DNS.
- Frontend redesign or frontend authentication changes.

Claude may read these areas for context but must not alter them in its first assignment.

### Expected first-assignment file scope

Likely files (create only when needed):
- `apps/api/README.md`
- `apps/api/pyproject.toml` (after runtime/tool choices are documented)
- `apps/api/tests/` (test scaffolding only)
- `docs/development/LOCAL_DEVELOPMENT.md`
- `docs/development/TESTING.md`
- `docs/development/ENVIRONMENT_VARIABLES.md`
- `docs/operations/DEPLOYMENT.md` (instructions only; no deployment action)
- `docs/operations/SECURITY.md` (document approved requirements; do not invent controls)
- `zensical.toml`
- relevant documentation workflow under `.github/workflows/`

Claude must not create empty directories merely to match a proposed tree.

## 5. Claude handoff requirements

The pull request description and final handoff must include:

1. Summary of completed work and explicit out-of-scope items.
2. Exact files created/changed.
3. Decisions proposed, with alternatives and rationale.
4. Approved Python runtime (3.12), package manager workflow (venv + pip), and pinned development/documentation tool versions.
5. Exact commands executed.
6. Test, lint, type-check and documentation-build results.
7. Any checks not run and why.
8. Known limitations, unresolved questions and risks.
9. Confirmation that no secrets, paid services, production resources or deployment actions were used.
10. Confirmation that no protected core files listed above were modified.

Claude must not mark the work complete if checks fail. Open a PR against `main`; do not merge it.

## 6. ChatGPT — core architecture and finalization ownership

After Claude's PR is ready, ChatGPT will inspect the diff and either request changes or accept the supporting work. ChatGPT then owns:

1. Final backend module boundaries and application structure.
2. FastAPI application factory/lifecycle, configuration validation and versioned routing.
3. Health endpoint, request correlation, structured logging and standardized error handling.
4. CORS and safe middleware configuration.
5. Pydantic contracts and initial approved endpoints.
6. Supabase integration, database design, migrations and RLS.
7. Cryptographic Supabase JWT verification, issuer/audience/expiry validation and key rotation handling.
8. Profile and preferences services/repositories and authenticated endpoints.
9. OpenAPI metadata, security schemes, Scalar route and docs accuracy.
10. Integration tests, authorization tests, cross-user isolation tests and migration verification.
11. Review and integration of Claude's documentation/tooling work.
12. Render deployment configuration, environment inventory and production smoke-test plan.
13. Final security review, API contract review, deployment readiness report and owner handoff.

The initial Phase 1 endpoint contract remains the four endpoints in `docs/IMPLEMENTATION_HANDOFF.md`:
- `GET /api/v1/health` — public.
- `GET /api/v1/me` — authenticated.
- `GET /api/v1/preferences` — authenticated.
- `PUT /api/v1/preferences` — authenticated.

Do not add future endpoints until the relevant feature contract is approved.

## 7. Integration and provider catalogue

This catalogue records the intended tools and API surfaces. It is not permission to create accounts, activate billing, or integrate every listed provider. Items marked **later** are not part of the initial backend foundation.

### A. AI / model inference — later phase

| Capability | Candidate | Intended use | Status |
|---|---|---|---|
| Vision + multimodal inference | Groq API; evaluate currently supported vision models | Read chart screenshots, extract visible chart facts and answer constrained visual questions | Candidate; benchmark before selection |
| Text reasoning / synthesis | Groq API; select a currently supported reasoning-capable model after evaluation | Synthesize specialist evidence and produce conditional scenarios | Candidate; exact model not frozen |
| Structured output | Model-provider JSON/structured-output capability plus Pydantic validation | Constrain model responses to validated schemas | Required design; verify model support |
| Fallback provider | None selected | Provider outage or model retirement handling | Do not add until justified |

Selection criteria: actual vision support, reasoning quality, structured-output reliability, context limits, latency, rate limits, free-tier quotas, data-retention/privacy terms and current pricing. Never assume a model is free or available based on old documentation. Do not hard-code a model name in business logic; use server-side configuration and a provider adapter. Record the model ID, evaluation date and benchmark results.

No AI calls are required for the initial Phase 1 foundation.

### B. Database, identity and file storage

| Capability | Selected service | API / interface | Status |
|---|---|---|---|
| Relational database | Supabase PostgreSQL | PostgreSQL connection from trusted backend; SQL migrations | Selected |
| Authentication | Supabase Auth | Supabase Auth API/SDK; signed JWT access tokens | Selected |
| Authorization | PostgreSQL RLS + backend authorization | SQL policies and verified JWT identity | Required |
| Private chart/file storage | Supabase Storage | Storage API with private buckets and signed access where appropriate | Later; selected platform candidate |
| Realtime updates | Supabase Realtime | Realtime channels | Not required for initial backend |
| Database schema migration | Supabase CLI / versioned SQL migrations | Migration files and CLI | Use after workflow is finalized |

Security: browser may use only public/publishable Supabase configuration. Service-role keys and database credentials stay server-side. RLS must be enabled and tested on exposed user-owned tables. A client-supplied user ID is never proof of identity.

### C. Market data — later phase

**Initial exchange:** Binance Spot. Gate 3 uses public market data only and does not require an API key or secret. The owner-approved freshness, integrity, recovery, rate-limit, provenance and fail-closed requirements are binding in `docs/development/GATE_3_MARKET_DATA.md`. Do not call private account endpoints or enable trading-related permissions.

Official public REST API surfaces to evaluate:
- `GET /api/v3/exchangeInfo` — symbol metadata, filters and trading status.
- `GET /api/v3/klines` — OHLCV candlestick history.
- `GET /api/v3/ticker/price` — latest price.
- `GET /api/v3/ticker/24hr` — 24-hour statistics.
- `GET /api/v3/ticker/bookTicker` — best bid/ask.
- `GET /api/v3/depth` — order book depth.
- `GET /api/v3/trades` and `GET /api/v3/aggTrades` — recent/aggregate trades, only if a later feature needs them.
- `GET /api/v3/time` — exchange server time.
- `GET /api/v3/ping` — connectivity check.

Public market-data-only host documented by Binance:
- REST: `https://data-api.binance.vision`
- WebSocket streams: `wss://data-stream.binance.vision`

WebSocket streams to consider later:
- `<symbol>@kline_<interval>` — live candle updates.
- `<symbol>@bookTicker` — best bid/ask updates.
- `<symbol>@depth` — depth updates when order-book analysis is approved.

Engineering requirements for later integration: respect current exchange rate limits and response headers, handle HTTP 429 and 418 safely, reconnect WebSockets, detect stale/discontinuous data, normalize timestamps and symbols, validate candle ordering, distinguish open from closed candles, and never interpret missing data as zero. Use REST for historical backfill and WebSocket only when live updates materially improve the product.

Potential secondary data providers (not selected): CoinGecko or CryptoCompare. Do not integrate a fallback until a concrete coverage/reliability requirement exists and current API terms/quotas are reviewed.

### D. Deterministic calculations — later phase

No external indicator API is required.

| Tool/library | Intended use | Status |
|---|---|---|
| Python standard library | Core utilities and validation | Use as appropriate |
| NumPy | Numerical operations | Candidate |
| Pandas | OHLCV series and time-series transformations | Candidate |
| Native Python indicator implementations | Auditable, deterministic indicators | Preferred where manageable |
| TA-Lib / pandas-ta | Optional indicator libraries | Evaluate only if a real need exists; do not add by default |

Indicators and risk calculations must be deterministic, tested against known fixtures and separated from LLM-generated interpretation. SMC/ICT, price action and Wyckoff logic are rule/definition modules, not third-party APIs.

### E. Chart ingestion and image processing — later phase

| Capability | Candidate | Status |
|---|---|---|
| Private image storage | Supabase Storage | Selected platform candidate |
| Upload validation | FastAPI/Python validation | Required when chart upload is approved |
| Image metadata/normalization | Pillow | Candidate; add only if needed |
| Vision interpretation | Selected Groq vision model via provider adapter | Model selection pending |
| Image safety/limits | Server-side content-type, size, dimensions and decoding checks | Required |

The browser must not send a permanent public chart URL to the model. Use a controlled backend flow and private storage access. Define file size, accepted formats, retention and deletion policy before enabling uploads.

### F. API and engineering documentation

| Capability | Tool | Status |
|---|---|---|
| Backend API framework | FastAPI | Selected |
| Request/response validation | Pydantic | Selected |
| Machine-readable API contract | FastAPI-generated OpenAPI | Authoritative |
| Interactive API reference | Scalar | Selected |
| Engineering documentation | Zensical | Selected |
| Schema migrations | SQL migration files + Supabase CLI | Selected direction |

Keep OpenAPI generated from actual FastAPI routes and schemas. Do not maintain a second manually edited API specification. Disable default Swagger UI and ReDoc routes as required by the implementation handoff; use the approved Scalar reference route.

### G. Hosting, source control and CI

| Capability | Service | Status |
|---|---|---|
| Frontend hosting | Vercel | Existing live frontend |
| Backend hosting | Render | Selected target |
| Database/Auth/Storage | Supabase | Selected |
| Source control | GitHub repository | Selected |
| CI | GitHub Actions | Selected |
| Documentation hosting | Undecided | Build locally/in CI until destination is approved |

Free service tiers may sleep, pause, impose quotas or lack production safeguards. Verify current plan limits before deployment; never promise production reliability from a free tier. Render's free web services currently have spin-down/instance limitations; Supabase free projects have quota and inactivity-pause limitations. Confirm current terms at deployment time.

### H. Monitoring and operational services — optional later

| Capability | Candidate | Status |
|---|---|---|
| Error monitoring | Sentry | Optional; no integration until privacy, quota and cost are reviewed |
| Structured application logs | Python standard logging / structured formatter | Core requirement |
| Metrics/tracing | OpenTelemetry | Later, only if operational complexity warrants it |
| Uptime monitoring | Platform health checks or a reviewed free monitor | Optional |
| Background jobs | No queue selected | Do not add until an asynchronous workload requires it |
| Cache | No Redis selected | Do not add until measured need justifies it |

### I. Services deliberately not required for Version 1 foundation

- Binance private account endpoints, trading permissions, or order endpoints. Gate 3 uses public market-data-only endpoints and requires no API credentials.
- Broker/MT5 APIs.
- Payment processors or billing.
- Email provider beyond the selected Supabase Auth configuration.
- Separate vector database.
- External indicator/signal provider.
- LangChain, CrewAI, Agno or another agent framework.
- MCP server.
- Redis, Celery, Kafka, RabbitMQ or Kubernetes.
- Paid monitoring, model or market-data subscriptions.

Revisit only with a documented requirement and owner approval.

## 8. API inventory discipline

The integration catalogue above lists provider APIs, not permission to expose all of them as Baymax application endpoints.

For every Baymax endpoint added later, document:
- Method and versioned path.
- Purpose and owning module.
- Authentication and authorization.
- Request schema and response schema.
- Success and error status codes.
- Validation and rate-limit behaviour.
- Data source/provenance and timestamp semantics.
- Tests and OpenAPI reference.

Initial Phase 1 application endpoints are only the four listed in Section 6. Future application APIs must be proposed and reviewed before implementation.

## 9. Definition of done

Claude's first assignment is complete only when:
- [ ] The PR contains only bounded supporting work.
- [ ] No protected core architecture/security files were changed.
- [ ] Documentation builds successfully.
- [ ] Python quality checks run successfully or have clearly recorded prerequisites.
- [ ] Tests are meaningful and do not fake product functionality.
- [ ] No credentials or secrets are present.
- [ ] No cloud service was provisioned and no paid plan activated.
- [ ] The complete handoff report is included.
- [ ] PR is open against `main` and not merged.

The backend as a whole is not deployable merely because Claude's first assignment is complete. Deployment readiness is determined only after ChatGPT's core implementation, integration review, security tests and owner-approved deployment verification.

## 10. Official references

Use official documentation and re-check current versions, quotas and model availability when implementing:
- FastAPI: https://fastapi.tiangolo.com/
- Pydantic: https://docs.pydantic.dev/
- Groq API: https://console.groq.com/docs
- Groq vision: https://console.groq.com/docs/vision
- Supabase: https://supabase.com/docs
- Supabase RLS: https://supabase.com/docs/guides/database/postgres/row-level-security
- Supabase Storage: https://supabase.com/docs/guides/storage
- Binance Spot API documentation: https://github.com/binance/binance-spot-api-docs
- Binance Spot REST API: https://developers.binance.com/en/docs/products/spot/rest-api
- Binance Spot WebSocket Streams: https://developers.binance.com/en/docs/products/spot/web-socket-streams
- Binance Spot market-data-only FAQ: https://developers.binance.com/en/docs/products/spot/market-data-only
- Baymax Gate 3 acceptance contract: docs/development/GATE_3_MARKET_DATA.md
- Scalar FastAPI integration: https://github.com/scalar/scalar
- Zensical: https://zensical.org/docs/
- Render: https://render.com/docs
- Vercel: https://vercel.com/docs
- GitHub Actions: https://docs.github.com/actions

**Final instruction:** Claude, perform only the first assignment in Section 4 after the owner explicitly authorizes that supporting-work start. Do not begin core backend implementation, Binance integration, AI integration, database/auth implementation, cloud provisioning, or deployment. Submit a reviewable PR and wait for ChatGPT/owner review.
