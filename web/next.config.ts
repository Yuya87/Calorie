import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // firebase-admin / @google/genai はサーバー側でのみ使う（バンドルしない）
  serverExternalPackages: ["firebase-admin", "@google/genai"],
  experimental: {
    // スピーチ音声のアップロード（元音声＋WAV）に備えて Server Actions の上限を引き上げ
    serverActions: { bodySizeLimit: "5mb" },
  },
};

export default nextConfig;
