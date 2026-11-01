import type { NextConfig } from "next";

// The Python API (button_nz.api.serve), proxied so the browser stays same-origin.
const API_URL = process.env.BUTTON_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
  // The map-first page moved from /explore to /; old links keep working.
  async redirects() {
    return [{ source: "/explore", destination: "/", permanent: true }];
  },
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
