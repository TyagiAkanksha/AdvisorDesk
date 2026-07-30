// Final review, finding C-2/F4: the client-side browser-navigation seam `lib/api/baseApi.ts`'s
// 401 interceptor needs, in its OWN module rather than colocated with its caller — a function
// mocked via `vi.mock`/`vi.spyOn` from a DIFFERENT module than the one calling it is a plain,
// reliable ESM import substitution; a function defined AND called within the very same module
// cannot be reliably intercepted that way (a known Vitest/ESM limitation — the caller closes
// over the original local binding at evaluation time, not whatever a mock later reassigns onto
// the module's exports object). jsdom's `window.location` is not reliably mockable/reassignable
// either (`Object.defineProperty`/reassignment is brittle across jsdom versions and pollutes
// global state across tests) — mocking THIS seam (`vi.mock('@/lib/authRedirect', ...)`), not
// `window.location` itself, is what a test spies on.
//
// `window.location.assign` (not `next/navigation`'s `useRouter`) is deliberate: this is called
// from `baseQueryWithReauth`, a plain function RTK Query's middleware invokes OUTSIDE any React
// component/hook tree — there is no `useRouter()` available there, so a full browser navigation
// via the native History API is the only seam that works regardless of which screen's
// query/mutation triggered it.
export function redirectToSignIn(): void {
  window.location.assign('/signin');
}
