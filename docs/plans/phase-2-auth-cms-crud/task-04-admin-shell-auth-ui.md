---
id: task-04
phase: phase-2-auth-cms-crud
depends_on: [phase-1-skeleton/task-04, task-01]
status: built
spec: advisordesk-prd.md §2.2, §5.1, §9
---

# task-04 — Admin shell, sign-in flow, RTK Query foundation

## Goal

The admin app has its authenticated shell (AppBar + Drawer nav), a sign-in page driving the §5.1
OAuth flow, a session guard rehydrated from `GET /auth/me`, and the RTK Query foundation
(`baseApi` + store + Providers) that every admin data screen (tasks 05–06, phase-5 panel) injects
endpoints into.

## Context (read ONLY these)

- `docs/FRONTEND-CONVENTIONS.md` §3–§6 (components, common layer, types boundary, admin data
  fetching).
- `apps/admin/src/types/generated/schema.d.ts` (post task-03 codegen) — DTO source.
- `advisordesk-prd.md` §5.1 (the four auth routes), §9 (cookie model — hence
  `credentials:'include'`).

## Files

- Create: `apps/admin/src/lib/{store.ts,hooks.ts}`, `apps/admin/src/lib/api/{baseApi.ts,authApi.ts}`
- Create: `apps/admin/src/app/providers.tsx`; modify `src/app/layout.tsx` (mount Providers)
- Create: `apps/admin/src/components/shell/AppShell/{Component.tsx,interface.ts,index.ts,Component.test.tsx}`
- Create: `apps/admin/src/components/auth/SignInScreen/{Component.tsx,index.ts,Component.test.tsx}`,
  `apps/admin/src/components/auth/RequireSession/{Component.tsx,interface.ts,index.ts,Component.test.tsx}`
- Create: `apps/admin/src/app/signin/page.tsx`, `apps/admin/src/app/(app)/layout.tsx` (thin:
  RequireSession + AppShell), `src/types/api/auth.ts`

## Interfaces

- **Consumes:** theme/common/Icon (p1-t04); API routes `auth_login`/`auth_me`/`auth_logout`
  (task-01) via codegen types.
- **Produces (later tasks rely on — produce exactly):**
  - `@/lib/api/baseApi`: `baseApi = createApi({ baseQuery: fetchBaseQuery({ baseUrl:
    process.env.NEXT_PUBLIC_API_URL, credentials: 'include' }), tagTypes:
    ['Content','Tags','Stats','Me'], endpoints: () => ({}) })` — all later endpoints inject here.
  - `@/lib/store` + typed `useAppDispatch`/`useAppSelector` in `@/lib/hooks`.
  - `@/lib/api/authApi`: `getMe` query (provides `['Me']`), `logout` mutation (invalidates all).
  - `@/types/api/auth.ts`: `export type MeDto = components['schemas']['MeResponse']`.
  - `AppShell` (children slot; nav: Dashboard, Content; user menu with avatar + sign-out) — the
    frame tasks 05/06 and phase-5's panel toggle mount into.
  - `RequireSession` (renders children when `getMe` succeeds; redirects to `/signin` on 401).

## Steps (TDD)

- [ ] **Step 1: Failing tests first** — `RequireSession.test` (jsdom; mock fetch): 401 →
  `router.replace('/signin')`; success → children rendered. `SignInScreen.test`: button labeled
  "Sign in with Google" links to `${API_URL}/api/v1/auth/login`. `AppShell.test`: nav links
  visible by role/name; sign-out calls the logout endpoint.
- [ ] **Step 2:** `pnpm -C apps/admin test` → FAIL.
- [ ] **Step 3: Implement** store/baseApi/authApi/Providers, then the three components (MUI via
  `common/` only), thin `signin/page.tsx` + `(app)/layout.tsx`.
- [ ] **Step 4:** run → PASS. **Step 5: Gates → commit:**
  `feat(admin): shell + signin + session guard + rtk foundation (phase-2 task-04)`

## Verify

```bash
pnpm -C apps/admin lint && pnpm -C apps/admin type-check && pnpm -C apps/admin test  # clean
pnpm -C apps/admin dev &   # /signin renders; / redirects to /signin without a session
grep -rn "credentials: 'include'" apps/admin/src/lib/api/baseApi.ts   # present
grep -rn "components\['schemas'\]" apps/admin/src | grep -v src/types  # empty (boundary holds)
```

## Acceptance

- Unauthenticated visits land on `/signin`; the button drives the real OAuth redirect; after
  callback the shell renders with the user's name/avatar from `getMe`; sign-out returns to
  `/signin`.
- All data flows through `baseApi` with cookies; no token ever touches JS.
- Types boundary + `@mui/*` import boundary hold (greps above).
