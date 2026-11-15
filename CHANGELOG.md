# Changelog

## Unreleased

- Added single-owner Argon2id password verification and signed, secure browser sessions.
- Connected the Baymax password screen to backend login, session restoration, and logout.
- Added a same-origin Vercel proxy for backend API and the planned private documentation route.
- Added authentication configuration and security guidance without storing plaintext credentials.

- Added interactive FastAPI Swagger UI at /docs and documented the OpenAPI schema at /openapi.json.
- Added tests for Swagger UI availability and its generated OpenAPI document link.
- Documented that API documentation must be protected or disabled before private endpoints are introduced.
- Added the first runnable FastAPI backend milestone with a public liveness endpoint.
- Added strict CORS configuration, request correlation, structured JSON logs, and standardized error responses.
- Prepared a Render Blueprint manifest without provisioning or deploying a service.
