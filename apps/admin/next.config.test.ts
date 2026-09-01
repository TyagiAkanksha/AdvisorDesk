import { describe, expect, it } from 'vitest';

import nextConfig from './next.config';

// Pins the WR-04 (task 6R-05) response-header interface. Design-pin rationale (CORRECTED —
// the cross-site-iframe clickjacking scenario was refuted by the verifier: Lax cookies aren't
// sent on cross-site iframe loads): the real drivers are the first-visit HTTP->HTTPS downgrade
// window (missing HSTS) and same-registrable-domain framing. Frame defense (X-Frame-Options /
// CSP frame-ancestors) is applied at the edge in infra/deploy/prod/Caddyfile, not here — this
// app-level config only carries the three headers Next can set directly on every response.
describe('next.config.ts', () => {
  it('applies HSTS + X-Content-Type-Options + Referrer-Policy to every route (WR-04, 6R-05)', async () => {
    const headersFn = nextConfig.headers;
    if (typeof headersFn !== 'function') {
      throw new Error('next.config.ts must export an async headers() function (WR-04, 6R-05)');
    }

    const headerGroups = await headersFn();

    expect(headerGroups).toHaveLength(1);
    expect(headerGroups[0].source).toBe('/(.*)');
    expect(headerGroups[0].headers).toHaveLength(3);
    expect(headerGroups[0].headers).toEqual(
      expect.arrayContaining([
        { key: 'Strict-Transport-Security', value: 'max-age=31536000; includeSubDomains' },
        { key: 'X-Content-Type-Options', value: 'nosniff' },
        { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
      ]),
    );
  });
});
