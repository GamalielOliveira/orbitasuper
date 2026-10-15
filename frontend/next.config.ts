import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // produção: gera .next/standalone (servidor Node enxuto para a imagem Docker)
  output: "standalone",
  // Celular via túnel (cloudflared): um único endereço serve site e API
  allowedDevOrigins: ["*.trycloudflare.com"],
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${process.env.BACKEND_URL || "http://localhost:8000"}/:path*` }];
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
