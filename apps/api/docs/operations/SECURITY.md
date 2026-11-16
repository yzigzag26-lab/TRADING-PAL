# Security boundaries

## Trust boundaries

- The browser is an untrusted client.
- The FastAPI backend is authoritative for protected API operations.
- Supabase Auth issues identity tokens. The backend must verify signature,
  issuer, audience where configured, and expiry before trusting identity.
- PostgreSQL row-level security and backend authorization must enforce
  user-scoped access.
- Provider credentials belong only in backend secret storage.

## Secrets

Never commit real credentials or expose service-role keys, database passwords,
JWT signing secrets, private Binance credentials, or AI-provider keys in browser
bundles, logs, documentation, prompts, or CI output. Templates contain
placeholders only.

## Private Baymax configuration schema

The `baymax` schema is private and is not exposed through the Supabase Data API.
The `app_settings` and `risk_settings` singleton tables have explicit table
ACLs and RLS policies:

- `baymax_app` receives SELECT, INSERT, and UPDATE policies only.
- The Render runtime login `baymax_runtime` inherits `baymax_app`, so it is
  covered by those policies and its existing table grants.
- No application DELETE policy exists; the runtime role has no DELETE grant.
- Supabase `anon`, `authenticated`, and `service_role` retain no schema/table
  access through this migration.
- The migration deliberately does not use FORCE ROW LEVEL SECURITY. The
  dedicated migration login owns the configuration tables and must be able to
  perform controlled schema migrations. PostgreSQL table owners bypass RLS
  unless FORCE is enabled; protect the migration credential as a privileged
  operator secret and never place it in Render or Vercel runtime settings.

RLS is defense in depth alongside schema isolation and explicit grants; it does
not replace backend authentication or authorization. Review migration
`20261116_0004` and its CI tests before applying it to the live database.

## Single-owner password authentication

Baymax has one password field and one owner; it does not use usernames, email addresses, registration, or OTP. The backend verifies the supplied password against an Argon2id hash stored in Render as `BAYMAX_PASSWORD_HASH`. The signing secret is stored separately as `BAYMAX_SESSION_SECRET`. Neither value belongs in Git, Vercel browser variables, logs, or chat.

The session is an eight-hour signed cookie named `__Host-baymax_session`, with `Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/`, and no `Domain` attribute. Vercel rewrites `/api/*` to Render so the browser sees a same-origin session. The login endpoint checks the request Origin against the configured CORS allow-list and applies a per-process failed-login limiter. Rotate `BAYMAX_SESSION_SECRET` to invalidate all outstanding sessions. Logout clears the current browser cookie; because the cookie is stateless, a copied token remains valid until expiry or secret rotation.

The initial limiter is process-local and is intended for the single-instance private service. If the service is scaled to multiple instances, move rate-limit state to a shared store before scaling.

## API documentation exposure

Swagger UI is currently available at /docs, and the generated OpenAPI
document is available at /openapi.json. Both are public at this foundation
stage because the only implemented operation is the public health endpoint.
Swagger UI is a testing interface, not an access-control boundary.

Before introducing any private API operation, either put both documentation
routes behind the backend authentication boundary or disable them in
production. The same restriction applies to future private schemas, examples,
and endpoint metadata. Never rely on CORS or an obscure URL to protect an API.

## Binance boundary

The later Binance integration is market-data-only. Use a dedicated read-only
key if the approved endpoint flow requires it. Never enable order, trading,
transfer, withdrawal, margin, or futures permissions. Public Spot market-data
endpoints may not require authentication; a personal key does not make public
market data private or account-specific.

## Operational controls

- Restrict CORS to known frontend origins.
- Never trust a client-supplied user ID as proof of identity.
- Test cross-user isolation and negative authorization cases before release.
- Do not log tokens, credentials, private chart contents, or sensitive payloads.
- Do not provision paid services or deploy production resources without owner
  approval.

Detailed controls must be implemented and evidenced with the backend work.
