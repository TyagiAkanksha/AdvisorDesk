import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

// `fetchBaseQuery` builds a `new Request(url, ...)` internally (even when
// `fetch` itself is mocked in tests) — the Fetch API's `Request` constructor
// throws on a bare relative URL with no base. Falls back to the documented
// local dev API origin (apps/admin/.env.local.example; FRONTEND-CONVENTIONS.md
// §1 pinned ports) so an unset `NEXT_PUBLIC_API_URL` never crashes request
// construction; every real deployment sets the env var.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// `fetchBaseQuery` always calls its `fetchFn` with a single pre-built
// `Request` object, never the conventional `fetch(url, init)` two-argument
// shape — but a `Request` instance stringifies to `"[object Request]"`
// (verified against this project's exact Node/undici version), not its URL.
// That breaks the standard `global.fetch = vi.fn(...)` mock pattern (used by
// this task's own component tests and every future RTK-Query-backed screen)
// whenever the mock inspects the call by string-matching the first
// argument's URL. Unpack the Request back into `fetch(url, init)` so mocked
// `fetch` always observes a plain URL string + a plain options object,
// matching what real browser `fetch` calls look like. Typed against the
// broader `RequestInfo` (matching native `fetch`'s own signature, which is
// what `fetchFn`'s declared type is checked against) even though
// `fetchBaseQuery` only ever actually calls this with a `Request`.
function fetchFn(input: RequestInfo, init?: RequestInit): Promise<Response> {
  if (input instanceof Request) {
    const requestInit: RequestInit & { duplex?: 'half' } = {
      method: input.method,
      headers: input.headers,
      credentials: input.credentials,
      body: input.body,
    };
    // Node/undici requires `duplex: 'half'` on any fetch() call whose body is
    // a ReadableStream (TS's bundled `RequestInit` type doesn't declare this
    // field yet, hence the local widened type above) — `getMe`/`logout` never
    // send a body today, but future mutation endpoints (tasks 05/06) will.
    if (input.body) {
      requestInit.duplex = 'half';
    }
    return fetch(input.url, requestInit);
  }
  return fetch(input, init);
}

// The single RTK Query root every domain slice injects endpoints into
// (docs/FRONTEND-CONVENTIONS.md §6). `credentials: 'include'` sends the
// HttpOnly admin session cookie (PRD §9) — no token is ever held in JS.
export const baseApi = createApi({
  baseQuery: fetchBaseQuery({
    baseUrl: API_BASE_URL,
    credentials: 'include',
    fetchFn,
  }),
  tagTypes: ['Content', 'Tags', 'Stats', 'Me'],
  endpoints: () => ({}),
});
