---
id: mcp-oauth-t09
phase: mcp-oauth
depends_on: [mcp-oauth-t08]
status: planned
spec: docs/plans/mcp-oauth/DESIGN.md
review: sonnet
---

# Task 09 — Admin "Connected apps" page (apps/admin)

## Goal

A new admin-app page at `/connected-apps` that lists every OAuth client from
`GET /api/v1/oauth/clients` (name, consent date, live tokens, last used, expiry) and lets the
admin **Revoke** one through a confirm dialog (`DELETE /api/v1/oauth/clients/{client_id}`).
Layered exactly like the existing Content list: RTK slice → VM hook → dumb screen → thin page.

## Context (read ONLY these)

- `docs/plans/mcp-oauth/DESIGN.md` §"Admin management UI".
- `docs/FRONTEND-CONVENTIONS.md` (all sections — layering §3, tests mock only the network edge §7).
- `apps/admin/src/lib/api/baseApi.ts` (`tagTypes`, `baseQueryWithReauth`), `apps/admin/src/lib/api/statsApi.ts`
  (smallest `injectEndpoints` example), `apps/admin/src/lib/api/contentApi.ts` lines 36–50
  (`deleteContent` mutation — the function-form `invalidatesTags`).
- `apps/admin/src/types/api/stats.ts` (how DTO aliases are declared from `components['schemas']`).
- `apps/admin/src/components/content/ContentListScreen/{useContentList.ts, Component.tsx, index.ts, deleteError.test.tsx}`
  and `components/ContentTable.tsx` (the `Box component="table"` table pattern, `ConfirmDialog` use).
- `apps/admin/src/components/common/index.ts` (what you may import; nothing else from MUI directly),
  `apps/admin/src/components/common/ConfirmDialog/interface.ts`.
- `apps/admin/src/lib/errorMessage.ts` (`extractErrorMessage`).
- `apps/admin/src/components/dashboard/DashboardScreen/Component.test.tsx` (test header: jsdom
  pragma, `requestUrl`, `jsonResponse`, `<Providers>` wrapper).
- `apps/admin/src/components/shell/AppShell/Component.tsx` (`NAV_ITEMS`) and
  `Component.test.tsx` lines 88–97 (the nav-links test you extend).
- `apps/admin/src/app/(app)/content/page.tsx` (thin page).
- `apps/admin/src/types/generated/schema.d.ts` — only to confirm `ConnectedApp` and
  `ConnectedAppsResponse` exist (task 08 generated them).

## Files

**Create**
- `apps/admin/src/types/api/connectedApps.ts`
- `apps/admin/src/lib/api/connectedAppsApi.ts`
- `apps/admin/src/components/connectedApps/ConnectedAppsScreen/interface.ts`
- `apps/admin/src/components/connectedApps/ConnectedAppsScreen/useConnectedApps.ts`
- `apps/admin/src/components/connectedApps/ConnectedAppsScreen/Component.tsx`
- `apps/admin/src/components/connectedApps/ConnectedAppsScreen/components/ConnectedAppsTable.tsx`
- `apps/admin/src/components/connectedApps/ConnectedAppsScreen/index.ts`
- `apps/admin/src/components/connectedApps/ConnectedAppsScreen/Component.test.tsx`
- `apps/admin/src/components/connectedApps/ConnectedAppsScreen/revoke.test.tsx`
- `apps/admin/src/app/(app)/connected-apps/page.tsx`

**Modify**
- `apps/admin/src/lib/api/baseApi.ts` — `tagTypes: ['Content', 'Tags', 'Stats', 'Me', 'ConnectedApps']`.
- `apps/admin/src/components/shell/AppShell/Component.tsx` — `NAV_ITEMS` gains
  `{ label: 'Connected apps', href: '/connected-apps' }` (third entry).
- `apps/admin/src/components/shell/AppShell/Component.test.tsx` — extend the nav-links test
  (rename to "shows Dashboard (/), Content (/content) and Connected apps (/connected-apps) nav
  links…") with `expect(screen.getByRole('link', { name: 'Connected apps' })).toHaveAttribute('href', '/connected-apps')`.

## Interfaces

**Consumes:** `components['schemas']['ConnectedApp']`, `components['schemas']['ConnectedAppsResponse']`
(t08 codegen); `baseApi`, `ConfirmDialog`, `EmptyState`, `ErrorState`, `LoadingIndicator`,
`Box`, `Button`, `Typography`, `PageContainer` from `@/components/common`; `extractErrorMessage`.

**Produces exactly:**

```ts
// src/types/api/connectedApps.ts
import type { components } from '@/types/generated/schema';
export type ConnectedAppDto = components['schemas']['ConnectedApp'];
export type ConnectedAppsResponseDto = components['schemas']['ConnectedAppsResponse'];

// src/lib/api/connectedAppsApi.ts
export const connectedAppsApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    getConnectedApps: builder.query<ConnectedAppsResponseDto, void>({
      query: () => '/api/v1/oauth/clients',
      providesTags: ['ConnectedApps'],
    }),
    revokeConnectedApp: builder.mutation<void, string>({
      query: (clientId) => ({ url: `/api/v1/oauth/clients/${encodeURIComponent(clientId)}`, method: 'DELETE' }),
      invalidatesTags: (_result, error) => (error ? [] : ['ConnectedApps']),
    }),
  }),
});
export const { useGetConnectedAppsQuery, useRevokeConnectedAppMutation } = connectedAppsApi;

// ConnectedAppsScreen/interface.ts  (the screen itself takes no props — it owns its VM hook like ContentListScreen)
export interface ConnectedAppsTableProps {
  items: ConnectedAppDto[];
  onRevoke: (app: ConnectedAppDto) => void;           // opens the confirm dialog; the hook performs the delete
}

// ConnectedAppsScreen/useConnectedApps.ts
export interface UseConnectedAppsResult {
  items: ConnectedAppDto[];
  isLoading: boolean;
  isError: boolean;
  hasData: boolean;                                   // same semantics as useContentList.hasData
  refreshErrorMessage: string | null;                 // background refetch failed with cached data (mirror useContentList)
  pendingRevoke: ConnectedAppDto | null;              // the app the confirm dialog is open for
  requestRevoke: (app: ConnectedAppDto) => void;
  cancelRevoke: () => void;
  confirmRevoke: () => Promise<void>;                 // unwrap(); on failure sets revokeErrorMessage, keeps dialog open
  isRevoking: boolean;
  revokeErrorMessage: string | null;
}
export function useConnectedApps(): UseConnectedAppsResult;
// REVOKE_ERROR_FALLBACK = "Couldn't revoke this app. Please try again."
// REFRESH_ERROR_FALLBACK = "Couldn't refresh connected apps — showing the last loaded list."
```

**Screen behaviour** (`Component.tsx`, dumb — renders hook state):
- `isLoading && !hasData` → `<LoadingIndicator />`; `isError && !hasData` → `<ErrorState message=… />`;
  `items.length === 0` → `<EmptyState title="No connected apps" description="Apps that connect over MCP (like Claude) will appear here after you approve them." />`.
- Otherwise `<Typography variant="h5">Connected apps</Typography>` + `<ConnectedAppsTable items onRevoke={requestRevoke} />`
  + `<ConfirmDialog open={pendingRevoke !== null} title="Revoke access?" body={`${name} will lose MCP access immediately. It can reconnect later by authorizing again.`} confirmLabel="Revoke" onConfirm={confirmRevoke} onClose={cancelRevoke} isPending={isRevoking} errorMessage={revokeErrorMessage ?? undefined} />`.
- Table columns (header text exact): `App`, `Approved`, `Access tokens`, `Refresh tokens`,
  `Last used`, `Expires`, and an unlabeled actions column holding a `Button` with accessible name
  `Revoke <client_name>` (`aria-label`). Dates render via `new Date(iso).toLocaleString()`; `null` → `—`.
  Row `data-testid={`connected-app-${client_id}`}`.

**Page:** `app/(app)/connected-apps/page.tsx` — `<PageContainer><ConnectedAppsScreen /></PageContainer>`.

## Steps (TDD)

- [ ] **RED — test-author** (vitest + RTL, mock ONLY `fetch`; header copied from the Dashboard test):
  - `Component.test.tsx`:
    - `renders one row per connected app with name, counts, and formatted dates` — fixture of
      two apps (one with `last_used_at: null`) → rows by `data-testid`; `—` for null; `Revoke Claude` button present.
    - `renders EmptyState when the list is empty`.
    - `renders LoadingIndicator while the first load is pending` (never-resolving fetch).
    - `renders ErrorState with the envelope message on a 500 first load` (`{"error":{"code":"internal","message":"boom"}}`).
    - `GET hits /api/v1/oauth/clients with credentials` — assert the recorded `Request.url` ends
      with `/api/v1/oauth/clients` and `credentials === 'include'`.
  - `revoke.test.tsx`:
    - `clicking Revoke opens the confirm dialog naming the app` — dialog role + `Revoke access?` + client name.
    - `confirming sends DELETE and the row disappears after refetch` — first GET returns two apps,
      DELETE 204, second GET returns one; assert the DELETE `Request.url` ends with
      `/api/v1/oauth/clients/adkc_abc` and `method === 'DELETE'`; the removed row is gone.
    - `a failed DELETE keeps the dialog open and shows the envelope message` — DELETE 500 with
      `{"error":{"code":"internal","message":"nope"}}` → dialog still open, `nope` visible, both rows remain.
    - `cancel closes the dialog without a request`.
  - `AppShell/Component.test.tsx` — extend the nav test as described.
  - Run `pnpm -C apps/admin test -- ConnectedApps AppShell` → RED (module not found / nav link missing).
- [ ] **GREEN — implementer:** types → slice (+ `tagTypes`) → hook → table → screen → index →
  page → nav item.
- [ ] `pnpm -C apps/admin type-check && pnpm -C apps/admin test` → PASS.
- [ ] `pnpm gates:admin` (root) → clean.
- [ ] Commit: `feat(admin): connected-apps page with revoke (mcp-oauth t09)`.

## Verify

```bash
pnpm gates:admin
pnpm -C apps/admin test -- ConnectedApps AppShell
```

## Acceptance

- The page lists apps from the real slice against a mocked `fetch`; revoke goes through
  `ConfirmDialog` and refetches on success, stays open with the message on failure.
- No MUI import outside `@/components/common`; no business logic in `Component.tsx`/table.
- Nav item present and asserted; `tagTypes` extended; codegen types (not hand-written) used.
- Reviewer (Sonnet) checks the five dimensions with file:line evidence.
