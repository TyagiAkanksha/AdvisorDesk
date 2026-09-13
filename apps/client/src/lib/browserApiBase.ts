// Browser-reachable API origin: this hook runs client-side, so (unlike `src/lib/publicApi.ts`'s
// server-only `API_URL`) it needs a `NEXT_PUBLIC_`-prefixed var to be inlined into the JS bundle
// at build time — the same mechanism/idiom `apps/admin/src/lib/apiBase.ts` already uses for its
// own (also browser-side) RTK Query base URL. Dev/test fall back to the documented local API
// origin so an unset var never blocks `pnpm dev`/`pnpm test`; production fails loudly at request
// time instead of silently shipping a request to `undefined/api/v1/public/chat`.
//
// phase-9 task-17 (DESIGN §A/D2): extracted verbatim from `useChatStream.ts` (it was a private
// `resolveApiBaseUrl` there) because `src/lib/feedbackApi.ts` is now a second browser-side caller
// that needs the exact same resolution. Deliberately NOT merged with `publicApi.ts`'s identical-
// looking `resolveApiBaseUrl` — that one reads the server-only `API_URL` for RSC fetches; the two
// differ in which env var they may read, and merging them would let a server-only value leak into
// a browser bundle path or vice versa.
const DEV_FALLBACK_API_URL = 'http://localhost:8000';

export function resolveBrowserApiBaseUrl(): string {
  const value = process.env.NEXT_PUBLIC_API_URL;
  if (value) {
    return value;
  }
  if (process.env.NODE_ENV === 'production') {
    throw new Error('NEXT_PUBLIC_API_URL must be set at build time');
  }
  return DEV_FALLBACK_API_URL;
}
