import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // Standalone server bundle for the shared infra/Dockerfile.web runtime
  // stage (phase-1 task-05): `next build` emits `.next/standalone` with a
  // self-contained `server.js` + pruned `node_modules`, so the runtime
  // image doesn't need the full workspace or a `pnpm install`.
  output: 'standalone',
};

export default nextConfig;
