import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  basePath: process.env.NEXT_PUBLIC_BASE_PATH || undefined,
  assetPrefix: process.env.STATIC_ASSET_PREFIX || undefined,
  images: { unoptimized: true },
  trailingSlash: true,
};

export default nextConfig;
