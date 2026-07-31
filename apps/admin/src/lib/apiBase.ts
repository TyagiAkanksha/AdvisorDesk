// Single source of truth for the apps/api base URL every admin consumer
// targets: `baseApi.ts` (RTK Query) and `SignInScreen` (the raw Google OAuth
// anchor href, which never goes through RTK Query). Review round 1 (I2):
// two independent inline reads of `process.env.NEXT_PUBLIC_API_URL` risked
// drifting, and — worse — a silent `undefined` fallback in a *build artifact*
// would render `href="undefined/api/v1/auth/login"` in production with no
// signal anything was wrong. Fail loudly at build/module-load time instead:
// a missing env var in a production build is a deploy-config bug, not a
// runtime edge case to degrade gracefully around.
//
// Dev/test keep the documented local API origin as a fallback so an unset
// var never blocks `pnpm dev`/`pnpm test` (apps/admin/.env.local.example;
// FRONTEND-CONVENTIONS.md §1 pinned ports; root .env.example mirrors the
// same default for the API side).
const DEV_FALLBACK_API_URL = 'http://localhost:8000';

function resolveApiBaseUrl(): string {
  const value = process.env.NEXT_PUBLIC_API_URL;
  if (value) {
    return value;
  }
  if (process.env.NODE_ENV === 'production') {
    throw new Error('NEXT_PUBLIC_API_URL must be set at build time');
  }
  return DEV_FALLBACK_API_URL;
}

export const API_BASE_URL: string = resolveApiBaseUrl();
