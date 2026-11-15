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
