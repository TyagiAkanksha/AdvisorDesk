import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// task-04 review round 1 (I2): `API_BASE_URL` is computed once at module
// load, so each case stubs env vars first, then `vi.resetModules()` +
// dynamic `import()` to force a fresh module evaluation against that env —
// mirroring the ordering trick `SignInScreen/Component.test.tsx` already
// relies on (static imports are hoisted ahead of same-file `process.env`
// assignment in ESM).
describe('apiBase', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it('exports NEXT_PUBLIC_API_URL verbatim when it is set', async () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', 'https://api.example.com');

    const { API_BASE_URL } = await import('./apiBase');

    expect(API_BASE_URL).toBe('https://api.example.com');
  });

  it('falls back to the local dev API origin when unset outside production', async () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', undefined);
    vi.stubEnv('NODE_ENV', 'test');

    const { API_BASE_URL } = await import('./apiBase');

    expect(API_BASE_URL).toBe('http://localhost:8000');
  });

  it('throws at module load when unset in production — never silently ships an undefined base URL', async () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', undefined);
    vi.stubEnv('NODE_ENV', 'production');

    await expect(import('./apiBase')).rejects.toThrow(
      'NEXT_PUBLIC_API_URL must be set at build time',
    );
  });
});
