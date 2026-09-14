import type { BaseQueryFn, FetchArgs, FetchBaseQueryError } from '@reduxjs/toolkit/query/react';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import { API_BASE_URL } from '@/lib/apiBase';
import { redirectToSignIn } from '@/lib/authRedirect';

const rawBaseQuery = fetchBaseQuery({
  baseUrl: API_BASE_URL,
  credentials: 'include',
});

// Guards against a real re-entrancy hazard, not just a belt-and-suspenders check:
// `api.util.resetApiState()` while a query's component is STILL SUBSCRIBED (e.g.
// `RequireSession`'s own `getMe` call — it doesn't unmount just because it 401'd) makes RTK
// Query notice the cache entry it's subscribed to vanished and immediately re-`initiate()` a
// fresh request to "heal" it (the same mechanism `vitest.setup.ts` documents). That healed
// request 401s again, which — with no guard — would dispatch `resetApiState()` again, which
// heals again, forever: an infinite request loop. In a real browser this is bounded by
// `window.location.assign` actually completing a navigation shortly after (tearing down this
// whole JS realm, module state included); jsdom's `location.assign` is a documented no-op
// (`Not implemented: navigation`, MDN/jsdom), so nothing ever tears the loop down there —
// confirmed empirically: without this guard, the pinned `RequireSession` 401 test alone runs
// the browser/store/fetch cycle until the Node process OOMs. One redirect per page load is
// also the only sane behavior anyway — no reason to keep resetting/refetching once we've
// already decided to leave.
let hasRedirected = false;

// Final review, finding C-2/F4: a session that expires MID-session (any later query or
// mutation, not just the initial `RequireSession` gate `GET /auth/me` already covers) used to
// dead-end — the failing call surfaced a generic "Sign in required." snackbar/error state with
// no path back to `/signin`, since nothing ever cleared the still-cached (stale) `Me`/other
// server-cache data or navigated the admin anywhere. Wrapping `fetchBaseQuery` here (the
// `baseQueryWithReauth` pattern RTK Query's own docs recommend for this exact shape of problem)
// intercepts a 401 from ANY endpoint, one time, in one place: reset the whole server cache
// (`api.util.resetApiState()` — so a subsequent `getMe` call actually refetches instead of
// re-serving stale cached data once the admin signs back in) and redirect to `/signin`.
// `credentials: 'include'` and every other `fetchBaseQuery` option stay exactly as before.
const baseQueryWithReauth: BaseQueryFn<string | FetchArgs, unknown, FetchBaseQueryError> = async (
  args,
  api,
  extraOptions,
) => {
  const result = await rawBaseQuery(args, api, extraOptions);

  if (result.error?.status === 401 && !hasRedirected) {
    hasRedirected = true;
    // Referencing `baseApi` here (defined below) is safe: this function only ever runs once RTK
    // Query actually dispatches a query/mutation, by which point the module has finished
    // evaluating and `baseApi` is fully initialized — the same forward-reference-via-closure
    // shape RTK Query's own "automatic re-authentication" recipe uses.
    api.dispatch(baseApi.util.resetApiState());
    redirectToSignIn();
  }

  return result;
};

// The single RTK Query root every domain slice injects endpoints into
// (docs/FRONTEND-CONVENTIONS.md §6). `credentials: 'include'` sends the
// HttpOnly admin session cookie (PRD §9) — no token is ever held in JS.
//
// Uses RTK Query's native fetch path: `fetchBaseQuery` calls the real global
// `fetch` with a pre-built `Request` object. A custom fetch override used to
// live here to unpack that `Request` back into a plain `fetch(url, init)`
// call, but it read the request body as a `ReadableStream` and re-passed it
// into a second `fetch()` call without ever consuming/tearing down the
// original — a browser hazard — and dropped any caller-supplied
// `AbortSignal` in the process (review round 1, C1/I1). The authored test
// mocks (`RequireSession`/`SignInScreen`/`AppShell` `Component.test.tsx`) are
// Request-aware and assert against the native `Request` shape directly, so
// no override is needed for `fetch` mocking to work in tests either.
export const baseApi = createApi({
  baseQuery: baseQueryWithReauth,
  tagTypes: ['Content', 'Tags', 'Stats', 'Me', 'ConnectedApps', 'WeakQueries'],
  endpoints: () => ({}),
});
