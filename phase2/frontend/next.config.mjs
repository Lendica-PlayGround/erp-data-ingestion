/** @type {import('next').NextConfig} */
const BACKEND = process.env.PHASE2_BACKEND_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  // Dev rewrites proxy defaults to a short timeout; handshake (map+codegen) can take many minutes.
  experimental: {
    proxyTimeout: 1_200_000, // 20 minutes (ms)
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND}/api/:path*` },
      { source: "/healthz", destination: `${BACKEND}/healthz` },
    ];
  },
};

export default nextConfig;
