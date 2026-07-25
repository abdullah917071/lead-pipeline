import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        // Backend (Uvicorn) binds 0.0.0.0:9000. localhost:9000 resolves to
        // 127.0.0.1 which is taken by MinIO (S3 AccessDenied), so we target
        // the LAN IP where Uvicorn actually answers.
        destination: "http://10.234.52.162:9000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
