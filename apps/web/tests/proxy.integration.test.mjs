import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { once } from "node:events";
import { createServer as createNetServer } from "node:net";
import { after, before, test } from "node:test";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ownerCookie = "__Host-baymax_session=integration-owner-session";
let backend;
let frontend;
let frontendOrigin;
let backendOrigin;
let backendRequests = [];

async function unusedPort() {
  const server = createNetServer();
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert.ok(address && typeof address === "object");
  const { port } = address;
  await new Promise((resolve, reject) =>
    server.close((error) => (error ? reject(error) : resolve())),
  );
  return port;
}

before(async () => {
  backend = createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    const body = Buffer.concat(chunks).toString("utf8");
    backendRequests.push({
      method: request.method,
      url: request.url,
      cookie: request.headers.cookie ?? "",
      body,
    });

    if (request.method === "POST" && request.url === "/api/v1/auth/login") {
      response.writeHead(200, {
        "content-type": "application/json",
        "cache-control": "no-store",
        "set-cookie": `${ownerCookie}; Path=/; Secure; HttpOnly; SameSite=Lax`,
      });
      response.end(JSON.stringify({ authenticated: true }));
      return;
    }

    if (request.method === "GET" && request.url === "/docs") {
      response.writeHead(200, { "content-type": "text/html" });
      response.end('<html><body>Swagger UI <div id="swagger-ui"></div><script>url="/openapi.json"</script></body></html>');
      return;
    }

    if (request.method === "GET" && request.url === "/openapi.json") {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({
        openapi: "3.1.0",
        paths: { "/api/v1/diagnostics/gate-3": { post: { summary: "Gate 3 diagnostics" } } },
      }));
      return;
    }

    if (request.method === "POST" && request.url === "/api/v1/diagnostics/gate-3") {
      if (request.headers.cookie !== ownerCookie) {
        response.writeHead(401, { "content-type": "application/json" });
        response.end(JSON.stringify({ detail: "Authentication is required." }));
        return;
      }
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({ status: "passed", checks: {} }));
      return;
    }

    response.writeHead(404);
    response.end();
  });
  backend.listen(0, "127.0.0.1");
  await once(backend, "listening");
  const backendAddress = backend.address();
  assert.ok(backendAddress && typeof backendAddress === "object");
  backendOrigin = `http://127.0.0.1:${backendAddress.port}`;

  const port = await unusedPort();
  frontendOrigin = `http://127.0.0.1:${port}`;
  frontend = spawn(
    process.execPath,
    [path.join(webRoot, "node_modules/next/dist/bin/next"), "dev", "--hostname", "127.0.0.1", "--port", String(port)],
    {
      cwd: webRoot,
      env: {
        ...process.env,
        BAYMAX_API_ORIGIN: backendOrigin,
        NEXT_TELEMETRY_DISABLED: "1",
      },
      stdio: "ignore",
    },
  );

  let ready = false;
  for (let attempt = 0; attempt < 90; attempt += 1) {
    if (frontend.exitCode !== null) {
      throw new Error(`Next.js exited before becoming ready (code ${frontend.exitCode}).`);
    }
    try {
      const response = await fetch(frontendOrigin);
      if (response.status < 500) {
        ready = true;
        break;
      }
    } catch {
      // The Next.js development server is still starting.
    }
    await delay(1000);
  }
  assert.equal(ready, true, "Next.js frontend did not become ready within 90 seconds.");
});

after(async () => {
  if (frontend && frontend.exitCode === null) {
    frontend.kill("SIGTERM");
    await Promise.race([once(frontend, "exit"), delay(5000)]);
    if (frontend.exitCode === null) frontend.kill("SIGKILL");
  }
  if (backend?.listening) {
    await new Promise((resolve, reject) =>
      backend.close((error) => (error ? reject(error) : resolve())),
    );
  }
});

test("frontend-domain Swagger keeps the owner session on the Render proxy request", async () => {
  const docs = await fetch(`${frontendOrigin}/docs`);
  assert.equal(docs.status, 200);
  assert.match(await docs.text(), /swagger-ui/i);

  const schema = await fetch(`${frontendOrigin}/openapi.json`);
  assert.equal(schema.status, 200);
  assert.ok((await schema.json()).paths["/api/v1/diagnostics/gate-3"]);

  const unauthenticatedDiagnostic = await fetch(
    `${frontendOrigin}/api/v1/diagnostics/gate-3`,
    { method: "POST" },
  );
  assert.equal(unauthenticatedDiagnostic.status, 401);

  const login = await fetch(`${frontendOrigin}/api/v1/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json", origin: frontendOrigin },
    body: JSON.stringify({ password: "test-only-owner-password" }),
  });
  assert.equal(login.status, 200);
  const setCookie = login.headers.get("set-cookie");
  assert.ok(setCookie?.startsWith(ownerCookie), "login response must set the owner session cookie");

  // Browsers keep this HttpOnly cookie automatically. The test forwards it as
  // a browser cookie jar would, without exposing it to frontend JavaScript.
  const diagnostic = await fetch(`${frontendOrigin}/api/v1/diagnostics/gate-3`, {
    method: "POST",
    headers: { cookie: ownerCookie },
  });
  assert.equal(diagnostic.status, 200);
  assert.equal((await diagnostic.json()).status, "passed");

  const diagnosticRequest = backendRequests.find(
    (entry) =>
      entry.method === "POST" &&
      entry.url === "/api/v1/diagnostics/gate-3" &&
      entry.cookie === ownerCookie,
  );
  assert.ok(
    diagnosticRequest,
    "authenticated diagnostic request must reach the Render-compatible upstream with the owner cookie",
  );
});
