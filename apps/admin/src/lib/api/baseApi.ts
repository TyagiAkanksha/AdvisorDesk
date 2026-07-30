import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import { API_BASE_URL } from '@/lib/apiBase';

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
  baseQuery: fetchBaseQuery({
    baseUrl: API_BASE_URL,
    credentials: 'include',
  }),
  tagTypes: ['Content', 'Tags', 'Stats', 'Me'],
  endpoints: () => ({}),
});
