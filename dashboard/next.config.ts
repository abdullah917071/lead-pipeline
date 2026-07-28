import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  basePath: "/dashboard",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:9000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
