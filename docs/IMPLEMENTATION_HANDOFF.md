# Trading Pal — Phase 1 Implementation Handoff

**Document status:** Prepared for owner review and approval  
**Plan baseline:** Phase 1, Revision 1.1  
**Scope:** Cloud-first application foundation only  
**Target repository:** `yzigzag26-lab/TRADING-PAL`  
**Implementation status:** Not started. This document does not authorize application code, cloud provisioning, or paid services.

---

## 1. Purpose and operating rules

This document is the implementation contract for the development agent(s) assigned to Phase 1. Follow it as the source of truth for scope, sequencing, architecture boundaries, verification, and handover.

Trading Pal is a private, mobile-first cryptocurrency intelligence application. Phase 1 establishes a secure, documented, deployable foundation. It does **not** implement trading intelligence or trading functionality.

### Non-negotiable rules

1. Work only in this repository. Do not create a competing repository or move the project elsewhere.
2. Read this handoff and all current architecture decisions before changing code.
3. Implement one phase at a time. A phase is complete only after its tests pass, evidence is recorded, documentation is updated, and the owner accepts its exit criteria.
4. Do not silently skip a failed test, weaken a security control, or mark an incomplete phase as complete.
5. Do not invent market prices, trading signals, chart analyses, users, balances, or history records. Empty states must be honest and clearly labelled.
6. Do not add features outside Phase 1. Record useful future ideas in a clearly labelled backlog instead.
7. Do not introduce microservices, message brokers, Kubernetes, agent frameworks, or unnecessary infrastructure. Use a modular monolith.
8. Never put secrets in source code, commits, issue comments, logs, screenshots, model prompts, or frontend bundles.
9. Never request or accept the user's Binance secret/API key during Phase 1. Binance integration is out of scope.
10. No paid service, subscription, upgrade, or usage-based resource may be activated without the owner's explicit approval.
11. Do not claim deployment, test, or security success without verifiable evidence.
12. Preserve the MIT licence and existing repository history.

### Approval boundary

The owner has approved Phase 1, Revision 1.1 and requested this handoff document. That approval authorizes preparation and review of this document only. **Do not begin application implementation or configure cloud services until the owner explicitly approves this handoff and the required account/service choices.**

---

## 2. Phase 1 objective and scope

### Objective

Deliver a production-oriented foundation with:

- A responsive Next.js web application deployed to Vercel.
- A Python FastAPI backend deployed to Render.
- Supabase-hosted PostgreSQL and Supabase Auth.
- Secure authenticated communication between frontend and backend.
- Versioned API contracts and interactive API reference.
- Comprehensive engineering documentation.
- Automated tests and CI checks.
- A repeatable deployment and developer onboarding process.

The initial experience must work on a real mobile phone and degrade gracefully on desktop/mobile network conditions.

### Included

- Monorepo structure and repository conventions.
- Next.js frontend shell, responsive navigation, and authentication screens/flows.
- FastAPI application foundation and versioned routes.
- Supabase Auth integration and backend JWT verification.
- PostgreSQL schema/migrations for the minimal Phase 1 entities.
- User-level data isolation and security tests.
- Preferences read/update endpoints.
- Health endpoint and authenticated current-user endpoint.
- OpenAPI generation and Scalar API reference.
- Zensical engineering documentation.
- CI, deployment configuration, environment-variable documentation, and handover.

### Explicitly excluded

- AI/LLM integration, model selection, prompts, agents, and orchestration.
- Chart upload, image interpretation, chart storage, and analysis reports.
- Binance market data, Binance account connection, API-key collection, and market scanning.
- Technical indicators, SMC/ICT, Wyckoff, quantitative analysis, or strategy generation.
- Trading execution, order placement, paper trading, portfolio management, or broker integrations.
- MCP server, external plugin integrations, and public developer API access.
- Notifications, billing, subscriptions, social/community features, and admin dashboards.
- Production market data or fabricated sample trading data.

Do not build placeholders that imply excluded capabilities are already functional. A clearly labelled “planned” or “not available in Phase 1” state is acceptable.

---

## 3. Approved baseline architecture

Use a **modular monolith**: one Next.js application and one FastAPI application, with clear internal boundaries.

| Concern | Selected technology | Responsibility |
|---|---|---|
| Frontend | Next.js + TypeScript | Mobile-first user interface |
| Frontend styling | Tailwind CSS | Responsive design system |
| Frontend authentication | Supabase Auth client with the supported SSR integration | Sign-in, sign-out, session lifecycle |
| Backend | Python 3.12 + FastAPI | API, authorization, business rules |
| Backend schemas | Pydantic | Input/output validation |
| Database | Supabase-hosted PostgreSQL | Persistent application data |
| Authentication provider | Supabase Auth | Identity and token issuance |
| Database migrations | Version-controlled SQL migrations | Reproducible schema changes |
| API contract | OpenAPI | Machine-readable API specification |
| API reference | Scalar | Interactive API reference; do not expose Swagger UI |
| Engineering docs | Zensical | Human-readable project documentation |
| Frontend hosting | Vercel | Web application deployment |
| Backend hosting | Render | FastAPI deployment |
| Source control and CI | GitHub + GitHub Actions | Review, automation, and traceability |

Use supported, stable releases at implementation time and commit lockfiles. Do not blindly install a prerelease or major version simply because it is newest. Record the selected versions in the repository.

### API documentation interface

- FastAPI remains the source of the OpenAPI specification.
- Expose the generated specification at a documented endpoint such as `/openapi.json`.
- Serve Scalar as the interactive API reference at a documented route such as `/reference`.
- Disable FastAPI's default Swagger UI route (`/docs`) and default ReDoc route (`/redoc`) unless the owner later requests otherwise.
- Do not hand-maintain a second, divergent API specification.
- Ensure schemas, descriptions, examples, security requirements, and error responses are represented in OpenAPI.

### Architecture constraints

- Frontend calls the backend through one central typed API client.
- The frontend must not connect directly to PostgreSQL.
- The frontend must not contain Supabase service-role credentials or database passwords.
- The backend is the authority for authorization and data access.
- The backend must derive the authenticated user identity from a verified token, never from a client-supplied user ID.
- Keep provider-specific logic behind integration boundaries where appropriate.
- Do not add a Redis/cache layer, task queue, or separate worker service without a reviewed requirement.

---

## 4. Required monorepo structure

Create the following structure incrementally. Do not create empty directories solely to make the tree look complete; add a directory when its first real file is needed.

```text
TRADING-PAL/
├── apps/
│   ├── web/
│   │   ├── src/
│   │   │   ├── app/
│   │   │   ├── components/
│   │   │   ├── features/
│   │   │   │   ├── auth/
│   │   │   │   ├── dashboard/
│   │   │   │   ├── markets/
│   │   │   │   ├── history/
│   │   │   │   └── settings/
│   │   │   ├── hooks/
│   │   │   ├── lib/
│   │   │   └── types/
│   │   ├── public/
│   │   ├── tests/
│   │   ├── package.json
│   │   └── README.md
│   └── api/
│       ├── app/
│       │   ├── api/v1/endpoints/
│       │   ├── core/
│       │   ├── database/
│       │   ├── models/
│       │   ├── schemas/
│       │   ├── services/
│       │   ├── integrations/
│       │   └── main.py
│       ├── migrations/
│       ├── tests/
│       ├── pyproject.toml
│       └── README.md
├── docs/
│   ├── architecture/
│   ├── api/
│   ├── development/
│   ├── operations/
│   ├── decisions/
│   ├── IMPLEMENTATION_HANDOFF.md
│   └── ... MkDocs pages and configuration
├── .github/
│   └── workflows/
├── .gitignore
├── .env.example
├── README.md
└── LICENSE
```

The exact internal files may be refined during implementation, but the separation between frontend, backend, tests, and documentation must remain clear.

### Required documentation set

At minimum, create and maintain:

- `README.md`: project purpose, scope, status, high-level architecture, links to documentation.
- `docs/architecture/SYSTEM_ARCHITECTURE.md`: components, trust boundaries, request flow, deployment topology.
- `docs/architecture/DATABASE_DESIGN.md`: entities, relationships, ownership, RLS approach, migration policy.
- `docs/api/API_STANDARDS.md`: versioning, naming, schemas, pagination policy if needed, errors, auth.
- `docs/api/ENDPOINTS.md`: endpoint inventory and links to live reference.
- `docs/development/LOCAL_DEVELOPMENT.md`: prerequisites and exact setup/run/test commands.
- `docs/development/TESTING.md`: test layers, commands, fixtures, acceptance evidence.
- `docs/development/ENVIRONMENT_VARIABLES.md`: each variable, purpose, required/optional status, where it belongs; never include real values.
- `docs/operations/DEPLOYMENT.md`: Vercel, Render, Supabase setup and release/rollback procedure.
- `docs/operations/SECURITY.md`: threat boundaries, secrets, JWT validation, CORS, RLS, logging, incident basics.
- `docs/decisions/DECISIONS.md` or individual ADR files: significant decisions and rationale.
- `CHANGELOG.md`: user-visible and engineering changes by release.
- `apps/web/README.md` and `apps/api/README.md`: service-specific development instructions.

Use Zensical to render the engineering documentation. The documentation deployment destination must be selected after checking the owner's actual free-tier/account eligibility. Do not assume a private GitHub repository can publish private Pages content on the current plan, and do not purchase a docs domain or hosting plan. Until a destination is approved, the docs must build locally and in CI.

---

## 5. Data model and security requirements

### Initial logical entities

Implement only the minimum entities needed for Phase 1:

1. `profiles`: application profile linked to the Supabase Auth user.
2. `user_preferences`: per-user application preferences.
3. `audit_logs`: narrowly scoped security/administrative event records, with sensitive values excluded.

Do not pre-create future trading tables merely because they appear in a roadmap. Future candidates such as chart uploads, market snapshots, analyses, risk assessments, broker connections, strategies, and orders require separate reviewed requirements.

### Database rules

- All schema changes must be committed as ordered, repeatable migrations.
- Define primary keys, foreign keys, uniqueness, nullability, timestamps, and indexes deliberately.
- Use UTC timestamps in storage and document display-time handling.
- Enforce ownership at the database layer with Row Level Security (RLS) where applicable.
- Test policies with at least two distinct authenticated users and an unauthenticated context.
- Do not treat an application-level `user_id` filter as a substitute for database security.
- If the backend uses a privileged database credential, document the privilege boundary and prove that user-scoped authorization cannot be bypassed by request parameters. Prefer a design that preserves enforceable user context/RLS.
- Never expose a service-role key to the browser.
- Do not log access tokens, refresh tokens, passwords, OTPs, connection strings, or secret environment values.

### Authentication rules

- Use Supabase Auth as the identity provider.
- Use the supported Next.js SSR/client integration and follow current Supabase guidance.
- The API must validate JWT signature, issuer, expiry, and expected audience/claims using the configured Supabase signing-key/JWKS approach. Handle key rotation safely.
- Do not merely decode a JWT; signature verification is mandatory.
- Return consistent 401 responses for missing, invalid, or expired credentials.
- Return 403 for authenticated users who lack permission.
- Protect authenticated routes on the backend even if the frontend also guards its pages.
- Test sign-in, sign-out, session refresh, invalid token, expired token, and cross-user access.
- Never store a separate password in the Trading Pal database.

### CORS and transport

- Allow only the explicitly configured frontend origin(s); do not use wildcard origins with credentials.
- Use HTTPS for deployed environments.
- Keep local development origins separate from production origins.
- Do not return stack traces or secret-bearing internal error details to clients.

---

## 6. API contract for Phase 1

All application endpoints must be under `/api/v1`. The health endpoint may be public; identity and preferences endpoints require authentication.

| Method | Endpoint | Auth | Expected behaviour |
|---|---|---|---|
| GET | `/api/v1/health` | Public | Liveness/health response without leaking infrastructure secrets |
| GET | `/api/v1/me` | Required | Return identity claims/profile for the verified current user |
| GET | `/api/v1/preferences` | Required | Return only the current user's preferences |
| PUT | `/api/v1/preferences` | Required | Validate and update only the current user's preferences |

Requirements:

- Define Pydantic request and response schemas for every endpoint.
- Define status codes and stable error response structure.
- Document authentication in OpenAPI.
- Add request validation, sensible payload limits, and safe error handling.
- Do not add endpoints for future features until their requirements are approved.
- Health checks must not expose environment variables, database credentials, token data, or detailed internal topology.
- The frontend must consume the API through a central client and typed contracts. Avoid duplicating response shapes in unrelated components.

---

## 7. Implementation sequence and phase gates

The sequence below is mandatory. Limited parallel work is allowed only where the dependency is explicit and shared contracts have already been agreed.

### Stage 0 — Repository and decision baseline

**Tasks**
- Confirm the repository and default branch.
- Preserve the licence and establish repository conventions.
- Add the approved project README and initial docs navigation.
- Confirm the supported Node.js and Python versions and package managers.
- Create the environment-variable inventory with names/purpose only.
- Record unresolved hosting-tier and documentation-hosting decisions.

**Exit gate**
- Structure and conventions are reviewed.
- No secrets are committed.
- No cloud service has been provisioned or paid for without permission.
- Owner accepts the implementation baseline.

### Stage 1 — Cloud and deployment foundation

**Tasks**
- Prepare Vercel frontend and Render backend deployment configurations.
- Prepare separate development and production environment settings.
- Connect GitHub deployment pipelines only after account access and project creation are approved.
- Add minimal frontend and backend health surfaces; do not add fake product data.
- Document deployment configuration and rollback.

**Verification**
- Both applications build from a clean checkout.
- Preview/deployment logs show the correct commit.
- HTTPS endpoints respond.
- Frontend can reach the backend using configured origins.
- Secrets exist only in approved secret stores.

**Exit gate**
- Owner can open the deployed frontend on a real phone.
- Backend deployment is healthy.
- No paid plan was activated without consent.

### Stage 2 — FastAPI and API documentation foundation

**Tasks**
- Implement FastAPI application startup and configuration.
- Add versioned routing, health endpoint, structured logging, request validation, and central error handling.
- Generate OpenAPI from actual routes and schemas.
- Integrate Scalar as the API reference.
- Disable default Swagger UI and ReDoc routes.
- Add API standards and endpoint documentation.

**Verification**
- OpenAPI JSON is valid and matches the implemented routes.
- Scalar loads and renders the API reference.
- Swagger UI is not exposed at the default `/docs` route.
- Health endpoint returns the documented response.
- Validation and error cases have automated tests.

**Exit gate**
- API contract is reviewed and frozen for frontend integration.
- API docs are accessible in the approved environment.

### Stage 3 — Supabase database and authentication foundation

**Tasks**
- Create/configure the Supabase project only after owner approval.
- Add schema migrations for profiles, preferences, and audit logs.
- Configure Supabase Auth and required redirect URLs.
- Implement backend JWT verification.
- Implement user-scoped data access and RLS policies.
- Document database structure, token verification, and security boundaries.

**Verification**
- Migrations apply cleanly to a fresh database.
- Authenticated user can access only their own profile/preferences.
- User A cannot read or update User B's records, even by manipulating request IDs or payloads.
- Unauthenticated requests cannot access protected routes.
- Invalid/expired tokens are rejected.
- Service-role credentials are absent from frontend assets and Git history.

**Exit gate**
- Security tests pass and owner reviews the data-isolation evidence.

### Stage 4 — Frontend foundation

**Tasks**
- Build a mobile-first responsive application shell.
- Implement approved navigation and initial screens: Login, Dashboard, Markets, History, and Settings.
- Implement authentication UI and session lifecycle using Supabase Auth.
- Provide explicit loading, error, empty, and unauthenticated states.
- Label unavailable future analysis capabilities as planned/not yet available.
- Do not fabricate market values, chart results, user activity, or history.

**Verification**
- Layout works at common mobile and desktop widths.
- Keyboard and screen-reader basics are respected.
- Auth state survives refresh as designed.
- Sign-out clears the session.
- Empty states are honest and useful.
- No secret or privileged key appears in browser bundles.

**Exit gate**
- Owner reviews the real-phone UI and authentication journey.

### Stage 5 — Frontend/backend integration

**Tasks**
- Implement the central typed API client.
- Attach current access tokens securely to protected requests.
- Handle 401, 403, validation failures, network errors, and server errors.
- Integrate current-user and preferences endpoints.
- Keep frontend types aligned with backend OpenAPI schemas.
- Document the complete request/session flow.

**Verification**
- Authenticated request succeeds.
- Unauthenticated request is rejected.
- Expired/invalid session is handled without a blank screen or infinite retry.
- User preferences persist and remain isolated.
- CORS rejects unapproved origins.
- No cross-user access is possible.

**Exit gate**
- End-to-end auth and preferences flows pass in deployed preview/staging.

### Stage 6 — Hardening, documentation, and handover

**Tasks**
- Run all frontend, backend, integration, and security tests.
- Run linting, formatting, type checks, dependency/build checks, and migration validation.
- Build Zensical documentation.
- Validate Scalar/OpenAPI output.
- Review environment-variable documentation and deployment instructions.
- Add a release changelog and record remaining known limitations.
- Capture evidence for each acceptance criterion.

**Verification**
- CI passes from a clean checkout.
- Documentation builds without errors.
- API reference matches deployed API version.
- Deployment and rollback instructions have been followed or rehearsed.
- No secrets or fake data are present.
- Owner can follow onboarding documentation.

**Exit gate**
- Owner reviews the evidence pack and explicitly accepts Phase 1.

---

## 8. Agent responsibilities and collaboration contract

One accountable lead agent must coordinate the work and maintain this handoff. Specialist agents may be assigned, but they must not independently change shared architecture or contracts.

| Role | Accountabilities | Must not |
|---|---|---|
| Lead / solution architect | Own phase sequencing, architecture consistency, decisions, reviews, and owner updates | Skip gates or silently change approved scope |
| Backend engineer | FastAPI, schemas, JWT verification, database access, migrations, backend tests, OpenAPI | Trust client-supplied identity or bypass authorization |
| Frontend engineer | Next.js UI, Supabase session flow, typed API client, responsive states, frontend tests | Access database directly or expose privileged secrets |
| QA / security reviewer | Test plans, auth and isolation tests, negative cases, acceptance evidence | Approve untested claims or weaken expected security |
| DevOps / documentation engineer | CI, Vercel/Render configuration, environment guides, Scalar, MkDocs, deployment docs | Provision paid services without consent or publish secrets |

### Coordination rules

- The lead agent owns the canonical API contract.
- Backend engineer defines schemas and endpoint behaviour first; frontend integration begins against the reviewed contract.
- Frontend and backend may work in parallel only after interfaces and ownership are clear.
- Do not have two agents edit the same files concurrently.
- Every handoff must include: changed files, decisions, commands run, test results, known issues, and next action.
- Every agent must read this file and the relevant docs before starting.
- Keep changes small and reviewable. Use descriptive commits and pull requests where practical.
- Do not merge a failing CI change.
- Ask the owner when a decision affects cost, privacy, scope, or an irreversible external configuration.

---

## 9. Dependencies and configuration inventory

### External dependencies

- GitHub repository access and Actions availability.
- Vercel account/project for the frontend.
- Render account/service for the backend.
- Supabase project for Auth and PostgreSQL.
- Approved environment variables and callback/redirect URLs.
- Domain configuration only if/when a domain is selected and controlled by the owner.

Before provisioning, record the account owner, selected plan, free-tier constraints, expected sleep/cold-start behaviour, usage limits, and any possible charges. Do not enter payment details or upgrade a plan without explicit permission.

### Environment-variable policy

Create `.env.example` with placeholder values and descriptions, never real credentials. Maintain the complete inventory in `docs/development/ENVIRONMENT_VARIABLES.md`.

Likely variable categories include:

- Frontend: public Supabase URL and public anon/publishable key; public API base URL.
- Backend: Supabase project URL/issuer/JWKS configuration; database connection configuration; allowed frontend origins; environment name and logging level.
- Deployment: platform-provided port and health-check configuration where required.

Exact variable names and whether a value is public or secret must be decided and documented during implementation. Never put a service-role key, database password, JWT signing secret, or private API credential in a `NEXT_PUBLIC_*` variable.

---

## 10. Testing strategy

Testing is a release requirement, not an optional final activity.

### Backend
- Unit tests for schemas, services, and error mapping.
- API tests for every endpoint and auth requirement.
- JWT tests: valid, missing, malformed, expired, wrong issuer/audience, and invalid signature.
- Database tests against an isolated test database or approved Supabase test project.
- Migration tests from an empty database.
- RLS/data-isolation tests using at least two users.
- CORS and input-validation tests.

### Frontend
- Component tests for auth and major UI states.
- Tests for loading, empty, validation, error, and unauthenticated states.
- API-client tests for token attachment and error handling.
- End-to-end tests for sign-in/session refresh/sign-out and preferences.
- Responsive checks on a real phone or browser device emulation, followed by owner verification on their phone.

### Integration and release
- Clean install/build for frontend and backend.
- Lint, format, type checks, and automated tests in GitHub Actions.
- OpenAPI schema validation and Scalar route check.
- MkDocs build check.
- Deployment smoke tests against the deployed commit.
- Secret scan and dependency vulnerability review using available CI tooling.
- Verify production configuration is not accidentally used by local tests.

Record exact commands, environment prerequisites, results, and any skipped tests. A skipped test must include a reason, risk, and owner-approved follow-up.

---

## 11. CI and branch standards

- Keep `main` deployable.
- Use short-lived feature branches and pull requests for implementation work.
- Suggested branch prefixes: `feat/`, `fix/`, `docs/`, `test/`, `chore/`.
- Require CI checks before merge where repository settings permit.
- CI should run relevant frontend/backend linting, type checks, tests, builds, OpenAPI validation, and documentation build.
- Never echo secrets in CI logs.
- Deploy only from approved branches/environments.
- Use separate preview/staging and production environment variables.
- Do not use force-push to rewrite shared history without owner approval.

---

## 12. Definition of Done and acceptance criteria

Phase 1 is complete only when every applicable criterion below is evidenced and accepted by the owner.

### Application and deployment
- [ ] Next.js frontend is deployed and usable on the owner's real phone.
- [ ] FastAPI backend is deployed and healthy.
- [ ] Frontend communicates with backend over HTTPS.
- [ ] Vercel/Render deployment is tied to the correct repository and commit.
- [ ] Free-tier limitations and any potential charges are documented.

### Authentication and data security
- [ ] Supabase Auth sign-in/sign-out/session lifecycle works.
- [ ] Backend cryptographically verifies Supabase JWTs.
- [ ] Protected endpoints reject missing, invalid, and expired tokens.
- [ ] User A cannot read or modify User B's private data.
- [ ] RLS and backend authorization are tested.
- [ ] No privileged secrets are exposed in frontend code, Git, or logs.
- [ ] CORS is restricted to approved origins.

### API and documentation
- [ ] All Phase 1 endpoints are versioned and tested.
- [ ] OpenAPI is generated from actual FastAPI routes and schemas.
- [ ] Scalar API reference works.
- [ ] Default Swagger UI and ReDoc routes are disabled.
- [ ] Zensical documentation builds successfully.
- [ ] Architecture, database, API, auth, security, environment, testing, and deployment docs are complete.
- [ ] Developer onboarding works from a clean checkout.
- [ ] Changelog and architecture decisions are maintained.

### Quality and scope
- [ ] CI passes.
- [ ] Automated backend, frontend, integration, and security tests pass.
- [ ] No fake trading data or fake analysis is displayed.
- [ ] No Phase 2+ intelligence or trading functionality has slipped into Phase 1.
- [ ] Known limitations and deferred work are documented.
- [ ] Owner has reviewed evidence and explicitly accepted the milestone.

A checkbox is not complete merely because code exists. Link it to a test result, deployment URL, document, screenshot, or review record.

---

## 13. Required handover report

At the end of each stage, the lead agent must provide:

1. Stage completed and commit/PR reference.
2. Files created or changed.
3. Architecture decisions made and their rationale.
4. Exact commands executed.
5. Test results, including failures and skipped tests.
6. Deployment URLs and the commit currently deployed, if applicable.
7. Security checks performed and evidence.
8. Documentation pages updated.
9. Known limitations and unresolved risks.
10. The next stage proposed, with its dependencies.
11. Any action requiring owner approval, especially cost or account configuration.

At final Phase 1 completion, include a clean setup walkthrough that a new developer can follow without private verbal instructions.

---

## 14. Future roadmap boundary

The architecture may reserve clean extension points for future work, but Phase 1 must not implement them.

Potential later stages, subject to separate approval:

- Market data ingestion and Binance public market-data integration.
- Chart uploads and image-analysis pipeline.
- Deterministic indicator and quantitative calculation modules.
- Specialist analysis modules and evidence synthesis.
- Risk engine and conditional scenarios.
- Historical benchmarking and paper trading.
- Broker adapters, MCP server, and external integrations.
- Any live trading capability only after separate security, legal, risk, and explicit owner approvals.

The future system must distinguish deterministic calculations from model-generated interpretation. Risk controls must ultimately be enforced by deterministic backend code, not overridden by an AI model.

---

## 15. Final instruction to the development agent

Your assignment is to implement the approved Phase 1 foundation exactly within the boundaries of this document. Do not start until the owner explicitly approves this handoff. After approval, begin at Stage 0, report the proposed work breakdown and dependencies, and wait for the owner's implementation-start confirmation before creating application code or provisioning services.

**Build a secure, testable, documented foundation. Do not optimise for speed by sacrificing correctness, security, or clarity.**
