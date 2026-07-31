import { configureStore } from '@reduxjs/toolkit';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { MeDto } from '@/types/api/auth';

// Final review, finding C-2/F4: a session expiring MID-session (any query/mutation AFTER the
// initial `RequireSession` gate, not just `getMe` itself) used to dead-end — a generic error
// with no path back to `/signin`, and stale cached data left behind. `baseQueryWithReauth`
// (lib/api/baseApi.ts) intercepts a 401 from ANY endpoint: reset the whole RTK Query cache and
// redirect to `/signin`.
//
// `@/lib/authRedirect` (not `window.location` — jsdom's `location` is not reliably
// mockable/reassignable, `vi.spyOn(window.location, 'assign')` throws "Cannot redefine
// property", confirmed empirically) is the seam this file mocks. It must be done via
// `vi.resetModules()` + `vi.doMock()` + a DYNAMIC `import()` inside each test, not the usual
// static top-level `vi.mock()`: `vitest.setup.ts` (this workspace's `setupFiles` entry, run for
// EVERY test file before that file's own module graph — including its `vi.mock` hoisting — is
// even processed) already imports `@/lib/api/baseApi` eagerly for its own `afterEach` cache
// reset. That import fully evaluates `baseApi.ts` (and therefore `authRedirect.ts`) with the
// REAL `redirectToSignIn` baked into `baseQueryWithReauth`'s closure before a static
// `vi.mock('@/lib/authRedirect', ...)` in this file would ever get a chance to apply — a plain
// `vi.mock` here is provably a no-op (confirmed empirically: `vi.isMockFunction` on the
// statically-imported binding was `true` in this file, yet `baseApi`'s internal call still hit
// the REAL implementation and crashed on `window is not defined` in this `environment: 'node'`
// file). `vi.resetModules()` clears vitest's module registry so the following dynamic
// `import()` calls force a FRESH evaluation of `authRedirect`/`baseApi` — which, at that point,
// resolves `vi.doMock`'s override. A local `configureStore` (not the shared `@/lib/store`
// singleton, which is still bound to the STALE, pre-reset `baseApi`) is built around that fresh
// `baseApi` so this test's dispatches actually flow through the mocked chain.
function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function pathnameOf(input: RequestInfo | URL): string {
  const url = input instanceof Request ? input.url : String(input);
  return new URL(url).pathname;
}

const meFixture: MeDto = {
  id: '11111111-1111-1111-1111-111111111111',
  email: 'ada@advisordesk.test',
  name: 'Ada Lovelace',
  avatar_url: null,
};

/** Fresh-imports `authRedirect` (mocked) + `baseApi`/`authApi`/`contentApi` (real, built on top
 * of the mock) and a local store wired to that fresh `baseApi` — see the module docstring above
 * for why this can't be the usual static `vi.mock`. */
async function freshMockedApis() {
  vi.resetModules();
  vi.doMock('@/lib/authRedirect', () => ({ redirectToSignIn: vi.fn() }));

  const { redirectToSignIn } = await import('@/lib/authRedirect');
  const { baseApi } = await import('@/lib/api/baseApi');
  const { authApi } = await import('@/lib/api/authApi');
  const { contentApi } = await import('@/lib/api/contentApi');

  const store = configureStore({
    reducer: { [baseApi.reducerPath]: baseApi.reducer },
    middleware: (getDefaultMiddleware) => getDefaultMiddleware().concat(baseApi.middleware),
  });

  return { redirectToSignIn, authApi, contentApi, store };
}

describe('baseApi 401 re-auth interceptor', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.doUnmock('@/lib/authRedirect');
  });

  it('a 401 from ANY endpoint (not just getMe) resets the whole cache and redirects to /signin', async () => {
    const { redirectToSignIn, authApi, contentApi, store } = await freshMockedApis();

    let getMeCalls = 0;
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async (input) => {
        const pathname = pathnameOf(input);
        if (pathname === '/api/v1/auth/me') {
          getMeCalls += 1;
          return jsonResponse(meFixture);
        }
        if (pathname.startsWith('/api/v1/content/')) {
          return jsonResponse(
            { error: { code: 'auth_required', message: 'Sign in required.' } },
            401,
          );
        }
        return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
      },
    );
    global.fetch = fetchMock;

    // Populate the cache with a real, successful getMe first (e.g. RequireSession's own gate,
    // earlier in a real session).
    await store.dispatch(authApi.endpoints.getMe.initiate());
    expect(getMeCalls).toBe(1);
    expect(authApi.endpoints.getMe.select()(store.getState()).data).toEqual(meFixture);

    // A DIFFERENT endpoint's MUTATION 401s — proves the interceptor is not special-cased to
    // getMe; this is the "mid-session expiry on any screen" case getMe's own 401 handling
    // (RequireSession) never covered.
    const deleteResult = await store.dispatch(
      contentApi.endpoints.deleteContent.initiate('some-content-id'),
    );
    expect('error' in deleteResult).toBe(true);

    expect(redirectToSignIn).toHaveBeenCalledTimes(1);
    expect(redirectToSignIn).toHaveBeenCalledWith();

    // State reset: the previously cached getMe data is gone.
    expect(authApi.endpoints.getMe.select()(store.getState()).data).toBeUndefined();

    // And a subsequent getMe call actually refetches — it does not re-serve stale cached data.
    await store.dispatch(authApi.endpoints.getMe.initiate());
    expect(getMeCalls).toBe(2);
  });

  it('a non-401 error does not reset the cache or redirect', async () => {
    const { redirectToSignIn, authApi, contentApi, store } = await freshMockedApis();

    let getMeCalls = 0;
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async (input) => {
        const pathname = pathnameOf(input);
        if (pathname === '/api/v1/auth/me') {
          getMeCalls += 1;
          return jsonResponse(meFixture);
        }
        return jsonResponse(
          { error: { code: 'internal_error', message: 'Database unreachable.' } },
          500,
        );
      },
    );
    global.fetch = fetchMock;

    await store.dispatch(authApi.endpoints.getMe.initiate());
    expect(getMeCalls).toBe(1);

    await store.dispatch(contentApi.endpoints.deleteContent.initiate('some-content-id'));

    expect(redirectToSignIn).not.toHaveBeenCalled();
    // Cache untouched by an unrelated 500: the earlier getMe result is still cached (no
    // refetch on a second call).
    expect(authApi.endpoints.getMe.select()(store.getState()).data).toEqual(meFixture);
    await store.dispatch(authApi.endpoints.getMe.initiate());
    expect(getMeCalls).toBe(1);
  });
});
