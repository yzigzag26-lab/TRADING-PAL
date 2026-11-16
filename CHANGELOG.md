# Changelog

## Unreleased

- Added the owner-approved Gate 3 Binance Spot market-data freshness and reliability acceptance contract. The contract requires a maximum price-event age of 3 seconds and strict refusal of trading decisions until required data is fresh and verified.
- Documented public Binance market-data-only REST/WebSocket access; removed the incorrect requirement to create or store Binance API credentials for public Spot market data.
- Added Gate 3 navigation, implementation status, and mandatory acceptance-test guidance to the canonical and Render-local Zensical documentation.
- Corrected the root project status to reflect the private single-owner authentication and database/configuration foundation already present in the repository.
- Added single-owner Argon2id password verification and signed, secure browser sessions.
- Connected the Baymax password screen to backend login, session restoration, and logout.
- Added a same-origin Vercel proxy for backend API and the planned private documentation route.
- Added authentication configuration and security guidance without storing plaintext credentials.
- Added interactive FastAPI Swagger UI at /docs and documented the OpenAPI schema at /openapi.json.
- Added tests for Swagger UI availability and its generated OpenAPI document link.
- Documented that API documentation must be protected or disabled before private endpoints are introduced.
- Added the first runnable FastAPI backend milestone with a public liveness endpoint.
- Added strict CORS configuration, request correlation, structured logs, and standardized error responses.
- Prepared a Render Blueprint manifest without provisioning or deploying a service.
