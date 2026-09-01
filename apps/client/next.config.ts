import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // Standalone server bundle for the shared infra/Dockerfile.web runtime
  // stage (phase-1 task-05): `next build` emits `.next/standalone` with a
  // self-contained `server.js` + pruned `node_modules`, so the runtime
  // image doesn't need the full workspace or a `pnpm install`.
  output: 'standalone',

  // Security response headers (WR-04, 6R-05). Design-pin rationale (CORRECTED — the
  // cross-site-iframe clickjacking scenario was refuted by the verifier: Lax cookies aren't
  // sent on cross-site iframe loads). The real drivers are the first-visit HTTP->HTTPS
  // downgrade window before a client has ever seen an HSTS response (missing HSTS), and
  // same-registrable-domain framing (a sibling host under the same registrable domain
  // embedding this app in a hidden iframe). Frame defense (X-Frame-Options / CSP
  // frame-ancestors) is applied at the edge in infra/deploy/prod/Caddyfile instead, since
  // Next can't cover the API origin — this app-level config only carries the three headers
  // Next can set directly on every response. No CSP here — a real CSP for the MUI/Emotion
  // inline-style stack needs its own design pass (follow-up); this task does not ship
  // `unsafe-inline` theater.
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'Strict-Transport-Security', value: 'max-age=31536000; includeSubDomains' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
        ],
      },
    ];
  },
};

export default nextConfig;
