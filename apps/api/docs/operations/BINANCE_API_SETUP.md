# Binance API credentials for Baymax

**Purpose:** Prepare a dedicated, read-only Binance API key for Baymax's future backend market-data integration.

**Important:** This guide does not ask you to share your API key or secret with anyone. Do not paste credentials into GitHub, chat, screenshots, frontend settings, or source files.

## 1. Understand the Spot API security distinction

Binance Spot REST endpoints declare their own security type:

- `NONE`: public market-data endpoint; no API key or signature is required.
- `USER_DATA`: private account information; requires an API key and signed request.
- `TRADE`: trading actions; requires trading permission and signed request.

A personal API key does **not** turn a `NONE` endpoint into private market data. Sending `X-MBX-APIKEY` to a `NONE` endpoint does not make the data account-specific or private. Binance's Spot API documentation defines this security model.

For Baymax, the product requirement is to configure your own Binance credentials on the backend and never use anonymous credentials belonging to someone else. We will send your API key on requests where Binance supports/requires API-key authentication. For Spot endpoints marked `NONE`, the exchange still treats the data as public market data. We must not claim otherwise.

The API secret is only needed to sign endpoints that require signatures. It is not needed to retrieve Spot endpoints marked `NONE`.

## 2. Create a dedicated Binance API key

1. Sign in to your Binance account using the official Binance website or app.
2. Open **Profile / Account** and find **API Management**. Menu wording may vary.
3. Create a new API key. Choose a system-generated key if Binance offers that option.
4. Give it a clear label, such as `Baymax-ReadOnly-MarketData`.
5. Complete Binance's required security verification.
6. Configure the key with the minimum permissions available:
   - Enable reading only, if the permission selector provides it.
   - Keep Spot & Margin Trading disabled.
   - Keep Futures disabled.
   - Keep withdrawals disabled.
   - Keep transfers and other account-operation permissions disabled.
7. If Binance offers IP access restrictions, prefer restricting the key to trusted IP addresses. Do not guess an IP address. For local development, use the actual trusted public egress IP you intend to use. Before production, inspect the Render service's outbound IP information and confirm Binance's accepted allowlist format. Render shared outbound ranges may contain multiple addresses; dedicated outbound IPs are a separate paid Render feature and are not approved for this project.
8. Save the key securely. Binance may show the secret only once.

If Binance's current API Management screen offers a specific **Market Data** permission, select only that permission. Do not enable account-data or trading permissions just to make a market-data request work.

## 3. Configure the local backend environment

1. Copy the root `.env.example` as a reference.
2. Create `apps/api/.env` for backend-only values. Do not commit this file.
3. Set:
   - `BINANCE_API_KEY` to your Binance API key.
   - `BINANCE_API_SECRET` to your Binance API secret.
   - `BINANCE_REST_BASE_URL` to `https://api.binance.com`.
   - `BINANCE_RECV_WINDOW_MS` to `5000` unless an approved implementation requires a different value.
4. Keep these values out of `apps/web/.env.local`. They must never use a `NEXT_PUBLIC_...` variable name.
5. Do not send the credentials to Claude Code or include them in an issue, pull request, commit, log, or screenshot.

The environment template is only a configuration inventory. It does not mean the Binance integration is implemented yet.

## 4. Add credentials to Render later

Do this only when the backend integration is implemented and the owner approves deployment:

1. Open the Baymax backend web service in Render.
2. Open its Environment settings.
3. Add `BINANCE_API_KEY` and `BINANCE_API_SECRET` as secret environment values.
4. Add the non-secret base URL and receive-window values.
5. Save and deploy only after the backend code is ready.
6. Never add Binance credentials to Vercel. The browser must call Baymax's backend; the backend calls Binance.

Before enabling Binance IP restrictions for Render, inspect the service's **Connect → Outbound** information and verify whether the Binance API Management allowlist can safely represent the applicable addresses. Do not buy a Render dedicated IP without explicit approval.

## 5. Security and operating rules

- Use a dedicated key for Baymax; do not reuse a key used by another application.
- Keep trading, withdrawals, transfers, margin and futures permissions disabled.
- Never expose the secret to the frontend or AI model.
- Never log request headers, API keys, signatures, or secret values.
- Redact credentials from exception messages and HTTP client diagnostics.
- Rotate/revoke the key immediately if it may have been exposed.
- Respect Binance rate limits. Back off on HTTP 429 and do not continue requests after an HTTP 418 ban response.
- Treat Binance data timestamps and source freshness explicitly. Do not interpret missing data as zero.

## Official references

- [Binance Spot REST API — General Information and Request Security](https://developers.binance.com/en/docs/products/spot/rest-api)
- [Binance API Management](https://www.binance.com/en/my/settings/api-management)
- [Render outbound IP addresses](https://render.com/docs/outbound-ip-addresses)
- [Render dedicated outbound IPs](https://render.com/docs/dedicated-ips)
