import type { NextConfig } from "next";

// Server-only override lets the proxy integration test use a local Render
// contract stub. Production continues to use the approved Render API origin.
const backendOrigin =
  process.env.BAYMAX_API_ORIGIN ?? "https://baymax-api-6b49.onrender.com";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backendOrigin}/api/:path*` },
      { source: "/guide", destination: `${backendOrigin}/guide/` },
      { source: "/guide/:path*", destination: `${backendOrigin}/guide/:path*` },
      { source: "/docs", destination: `${backendOrigin}/docs` },
      { source: "/docs/:path*", destination: `${backendOrigin}/docs/:path*` },
      { source: "/openapi.json", destination: `${backendOrigin}/openapi.json` },
    ];
  },
};

export default nextConfig;
