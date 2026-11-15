import type { NextConfig } from "next";

const backendOrigin = "https://baymax-api-6b49.onrender.com";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backendOrigin}/api/:path*` },
      { source: "/guide", destination: `${backendOrigin}/guide/` },
      { source: "/guide/:path*", destination: `${backendOrigin}/guide/:path*` },
      { source: "/openapi.json", destination: `${backendOrigin}/openapi.json` },
    ];
  },
};

export default nextConfig;
