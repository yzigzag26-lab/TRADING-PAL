# Security boundaries

## Trust boundaries

- The browser is an untrusted client.
- FastAPI is authoritative for the private single-owner session and protected
  application operations.
- Current login uses an Argon2id owner-password hash and a signed,
  `HttpOnly` session cookie. The current application does not use Supabase
  Auth/JWT login.
- Supabase PostgreSQL stores application data in the private `baymax` schema.
  Keep database credentials server-side and preserve the explicit role/grant
  boundaries documented in the Gate 1/2 database records.
- Provider credentials belong only in backend secret storage. Gate 3 Binance
  public market-data access requires no API key or secret.

## Secrets

Never commit real credentials or expose database passwords, session-signing
secrets, Supabase service-role credentials, or future AI-provider keys in
browser bundles, logs, documentation, prompts, or CI output. Templates contain
placeholders only.

## Single-owner password authentication

Baymax has one password field and one owner; it does not use usernames, email
addresses, registration, or OTP. The backend verifies the supplied password
against an Argon2id hash stored in Render as `BAYMAX_PASSWORD_HASH`. The
signing secret is stored separately as `BAYMAX_SESSION_SECRET`. Neither value
belongs in Git, Vercel browser variables, logs, or chat.

The session is an eight-hour signed cookie named `__Host-baymax_session`,
with `Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/`, and no `Domain`
attribute. Vercel rewrites `/api/*` to Render so the browser sees a same-origin
session. The login endpoint checks the request Origin against the configured
CORS allow-list and applies a per-process failed-login limiter. Rotate
`BAYMAX_SESSION_SECRET` to invalidate all outstanding sessions. Logout clears
the current browser cookie; because the cookie is stateless, a copied token
remains valid until expiry or secret rotation.

The initial limiter is process-local and is intended for the single-instance
private service. If the service is scaled to multiple instances, move
rate-limit state to a shared store before scaling.

## API documentation exposure

Swagger UI is currently available at `/docs`, and the generated OpenAPI
document is available at `/openapi.json`. Both are public at this foundation
stage. The documented operations are public liveness and the single-owner
authentication lifecycle: login (password required and trusted-Origin checked),
session-status (returns only an authentication boolean), and logout
(trusted-Origin checked). No private market, account, or trading operations
are currently exposed.

Swagger UI is a testing interface, not an access-control boundary. Before
introducing any private API operation, either protect both documentation routes
behind the owner authentication boundary or disable them in production. The
same restriction applies to future private schemas, examples, and endpoint
metadata. Never rely on CORS or an obscure URL to protect an API.

## Binance boundary

Gate 3 uses Binance Spot public market-data-only REST and WebSocket endpoints.
These public endpoints do not require an API key, secret, signature, or account
permissions. Do not create Binance credentials for Gate 3 and do not call
private account, user-data, trading, transfer, withdrawal, margin, or futures
endpoints.

The binding freshness, integrity, recovery, rate-limit and fail-closed rules
are in [Gate 3 — Binance Spot market data](../development/GATE_3_MARKET_DATA.md).

## Operational controls

- Restrict CORS to known frontend origins.
- Never trust a client-supplied user ID as proof of identity.
- Keep PostgreSQL runtime and migration credentials separate.
- Do not log tokens, credentials, private chart contents, or sensitive payloads.
- Do not provision paid services or deploy production resources without owner
  approval.
- Test failure paths and negative authorization cases before release.

Detailed controls must be implemented and evidenced with the backend work.
