# Baymax Backend — Claude Code Work Order

**Repository:** `yzigzag26-lab/TRADING-PAL`  
**Product:** Baymax (the product is still named Trading Pal in the repository)  
**Frontend:** https://baymax-nu.vercel.app  
**Backend target:** Python + FastAPI on Render  
**Database/Auth/Storage:** Supabase  
**Status:** Work allocation and integration catalogue; not a deployment authorization.

## 1. Purpose and authority

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
2. No Binance integration during Phase 1. For the later, separately approved market-data phase, the owner has chosen to configure a dedicated personal Binance API key on the backend. Never put it in the frontend, Git, logs, prompts, or CI. Binance Spot endpoints marked `NONE` remain public even if an API-key header is supplied; the key does not make their data private or account-specific. Do not enable private account, trading, transfer, margin, futures, or withdrawal permissions for market-data retrieval.
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
- Document the API documentation workflow: FastAPI-generated OpenAPI is authoritative; Scalar is the interactive reference; MkDocs Material is the human-readable engineering documentation.
- Record unresolved decisions instead of guessing.

B. **Python quality-tooling foundation**
- Propose and configure Python formatting/linting, static type checking and test tooling.
- Preferred candidates: Ruff for lint/format and pytest for tests; propose the type checker and explain its trade-offs before locking it in.
- Keep tool configuration small and compatible with the chosen Python runtime.
- Do not invent an unapproved Python version or package manager. Record the proposed versions and wait for approval if a choice affects deployment/runtime compatibility.

C. **Test infrastructure scaffolding**
- Establish pytest configuration and a minimal test layout/fixtures.
- Add only tests for tooling/configuration scaffolding or documentation build checks that can be meaningfully verified without a real Supabase project.
- Do not create fake business behaviour or tests that pass by mocking away all meaningful logic.
- Do not create fake database credentials or require production secrets to run local tests.

D. **Documentation build**
- Add MkDocs Material configuration and navigation for existing/approved documentation.
- Ensure docs build locally and in CI.
- Keep the docs hosting destination undecided until account/plan eligibility is checked and approved.

E. **CI preparation**
- Add or extend GitHub Actions for documentation build and safe Python static checks.
- Do not add deployment workflows, publish artifacts publicly, or configure production secrets.
- CI must not print environment values or credentials.

F. **Backend package metadata**
- Prepare a minimal backend project metadata file only after documenting the proposed Python runtime and dependency/package-manager choice.
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
- `mkdocs.yml`
- relevant documentation workflow under `.github/workflows/`

Claude must not create empty directories merely to match a proposed tree.

## 5. Claude handoff requirements

The pull request description and final handoff must include:

1. Summary of completed work and explicit out-of-scope items.
2. Exact files created/changed.
3. Decisions proposed, with alternatives and rationale.
4. Python runtime, package manager and dependency versions proposed.
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

**Initial exchange:** Binance Spot. The owner has chosen to use a dedicated personal Binance API key for the later market-data integration, configured only in the trusted backend. This is explicitly out of Phase 1 scope. Binance Spot endpoints marked `NONE` do not require authentication; sending the owner's API-key header does not make those responses private or account-specific. Do not request or use private account endpoints or enable trading-related permissions. The exact endpoints and authentication behaviour must be verified against current Binance documentation when that phase is approved.

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
| Engineering documentation | MkDocs Material | Selected |
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

- Binance private account endpoints, trading permissions, or order endpoints. The owner's dedicated read-only API-key configuration for the later public market-data integration is documented separately and remains out of Phase 1.
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
- Binance public market-data-only endpoints: https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md
- Scalar FastAPI integration: https://github.com/scalar/scalar
- MkDocs Material: https://squidfunk.github.io/mkdocs-material/
- Render: https://render.com/docs
- Vercel: https://vercel.com/docs
- GitHub Actions: https://docs.github.com/actions

**Final instruction:** Claude, perform only the first assignment in Section 4 after the owner explicitly authorizes that supporting-work start. Do not begin core backend implementation, Binance integration, AI integration, database/auth implementation, cloud provisioning, or deployment. Submit a reviewable PR and wait for ChatGPT/owner review.
