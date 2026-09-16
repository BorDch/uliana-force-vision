import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  assetPrefix: process.env.STATIC_ASSET_PREFIX || undefined,
  trailingSlash: true,
};

export default nextConfig;
