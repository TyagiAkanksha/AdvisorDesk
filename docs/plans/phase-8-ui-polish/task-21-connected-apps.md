---
id: p8-t21
phase: phase-8-ui-polish
depends_on: [p8-t18]
status: pending
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: sonnet
---

# Task 21 — Connected apps: header, focused table, red revoke, refresh feedback (C6)

## Goal

The MCP "Connected apps" page gets the same treatment as the content list: `PageHeader` with a
one-line description, an outlined MUI table reduced to what an admin acts on — Client (name +
short id) · Connected · Last used · Revoke (outlined, error colour) — a table-shaped skeleton,
the empty state under the header (not instead of it), a destructive confirm, a "Access
revoked" success notice, and a snackbar when a background refetch fails (closes F-5).

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §2, §5 C6.
- `docs/FRONTEND-CONVENTIONS.md` §3, §7, §9.
- `apps/admin/src/components/connectedApps/ConnectedAppsScreen/{Component.tsx, useConnectedApps.ts,
  components/ConnectedAppsTable/*, Component.test.tsx, revoke.test.tsx}` — rewritten/migrated
  here; pins listed below. `revoke.test.tsx` relies on the row `data-testid="connected-app-
  <client_id>"` and the `Revoke <name>` button names — both are kept.
- `apps/admin/src/components/common/{PageHeader,TableContainer,Table,TableHead,TableBody,TableRow,
  TableCell,Paper,Typography,Button,Skeleton,EmptyState,ErrorState,ConfirmDialog}/`, `useSnackbar`.
- `apps/admin/src/lib/{format.ts, copy.ts, errorMessage.ts}`, `lib/api/connectedAppsApi.ts`,
  `types/api/connectedApps.ts` (`ConnectedAppDto`: `client_id`, `client_name`,
  `consent_granted_at: string | null`, `last_used_at: string | null`, …).

## Files

**Create**
- `src/components/connectedApps/ConnectedAppsScreen/components/ConnectedAppsSkeleton/{Component.tsx, index.ts}`

**Modify**
- `src/components/connectedApps/ConnectedAppsScreen/{Component.tsx, useConnectedApps.ts}`
- `src/components/connectedApps/ConnectedAppsScreen/components/ConnectedAppsTable/Component.tsx`
- `src/components/connectedApps/ConnectedAppsScreen/{Component.test.tsx, revoke.test.tsx}`
- `src/lib/copy.ts`

## Interfaces

```ts
// src/lib/copy.ts additions
// CONNECTED_APPS_TITLE ('Connected apps') already exists (task 15 — nav label = page title)
export const CONNECTED_APPS_DESCRIPTION =
  'Apps authorised to use AdvisorDesk over MCP (for example Claude). Revoking removes their access immediately.';
export const CONNECTED_APPS_TABLE_LABEL = 'Connected apps';
export const NO_CONNECTED_APPS_TITLE = 'No connected apps';
export const NO_CONNECTED_APPS_DESCRIPTION =
  'Apps that connect over MCP (like Claude) will appear here after you approve them.';
export const REVOKE_LABEL = 'Revoke';
export const REVOKE_DIALOG_TITLE = 'Revoke access?';
export const ACCESS_REVOKED_MESSAGE = 'Access revoked';
export const CONNECTED_APPS_LOAD_ERROR = "Couldn't load connected apps.";
export const CONNECTED_APPS_REFRESH_ERROR = "Couldn't refresh connected apps — showing the last loaded list.";
export const REVOKE_ERROR_FALLBACK = "Couldn't revoke this app. Please try again.";

// useConnectedApps.ts — result shape unchanged EXCEPT: confirmRevoke success now calls
// useSnackbar().success(ACCESS_REVOKED_MESSAGE); a background refetch failure (hasData && isError,
// rising edge) calls useSnackbar().error(CONNECTED_APPS_REFRESH_ERROR) once. The hook-local
// fallback strings move to copy.ts.

// ConnectedAppsTable — props unchanged { items, onRevoke }. Render:
// <TableContainer component={Paper} variant="outlined" sx={{ overflowX: 'auto' }}>
//   <Table aria-label={CONNECTED_APPS_TABLE_LABEL}>
//     head: Client | Connected | Last used | Actions(align right)
//     row (`hover`, data-testid={`connected-app-${client_id}`}):
//       Client cell = two stacked lines:
//         <Typography variant="body2" component="div">{client_name}</Typography>
//         <Typography variant="caption" color="text.secondary" component="div">{client_id.slice(0, 12)}</Typography>
//       | {formatOptionalDateTime(consent_granted_at)} | {formatOptionalDateTime(last_used_at)} |
//       <Button variant="outlined" color="error" size="small" aria-label={`Revoke ${client_name}`} onClick>{REVOKE_LABEL}</Button>
// (Access/refresh-token counts and "Expires" are dropped — DESIGN.md §C6.)

// ConnectedAppsSkeleton — zero-prop: same TableContainer/Table head + 3 rows of `Skeleton variant="text"`
// cells; container `role="status" aria-label={LOADING_LABEL}`.
```

**Screen render (exact structure):**

```tsx
const { items, isLoading, isError, hasData, errorMessage, pendingRevoke, requestRevoke, cancelRevoke, confirmRevoke, isRevoking, revokeErrorMessage } = useConnectedApps();
return (
  <Box>
    <PageHeader title={CONNECTED_APPS_TITLE} description={CONNECTED_APPS_DESCRIPTION} />
    {isLoading && !hasData ? <ConnectedAppsSkeleton /> : null}
    {isError && !hasData ? <ErrorState message={errorMessage ?? CONNECTED_APPS_LOAD_ERROR} /> : null}
    {hasData && items.length === 0 ? <EmptyState icon="Link" title={NO_CONNECTED_APPS_TITLE} description={NO_CONNECTED_APPS_DESCRIPTION} /> : null}
    {hasData && items.length > 0 ? <ConnectedAppsTable items={items} onRevoke={requestRevoke} /> : null}
    <ConfirmDialog
      open={pendingRevoke !== null}
      title={REVOKE_DIALOG_TITLE}
      body={`${pendingRevoke?.client_name ?? ''} will lose MCP access immediately. It can reconnect later by authorizing again.`}
      confirmLabel={REVOKE_LABEL}
      onConfirm={confirmRevoke}
      onClose={cancelRevoke}
      isPending={isRevoking}
      errorMessage={revokeErrorMessage ?? undefined}
      destructive
    />
  </Box>
);
```

The header renders in EVERY state (today it only renders with rows; the `heading level 1`
pin below moves accordingly).

## Steps (TDD)

- [ ] **RED — test-author.** In `Component.test.tsx` rewrite the first pin (`renders one row
  per connected app with name, counts, and formatted dates`) as the two cases below, rewrite
  the loading pin, and append the header/empty-state cases; add `formatDateTime` import from
  `@/lib/format`. In `revoke.test.tsx` append one case. All other assertions stay.

```tsx
  it('renders the header and one row per app: client name + short id, connected and last-used dates', async () => {
    global.fetch = vi.fn(async () => jsonResponse(listFixture));

    renderScreen();

    expect(await screen.findByRole('heading', { level: 1, name: 'Connected apps' })).toBeInTheDocument();
    expect(
      screen.getByText(/Apps authorised to use AdvisorDesk over MCP/),
    ).toBeInTheDocument();

    const table = screen.getByRole('table', { name: 'Connected apps' });
    const headers = within(table).getAllByRole('columnheader').map((cell) => cell.textContent);
    expect(headers).toEqual(['Client', 'Connected', 'Last used', 'Actions']);

    const rowA = screen.getByTestId('connected-app-adkc_abc');
    expect(within(rowA).getByText('Claude')).toBeInTheDocument();
    expect(within(rowA).getByText('adkc_abc')).toBeInTheDocument();
    expect(within(rowA).getByText(formatDateTime(appA.consent_granted_at as string))).toBeInTheDocument();
    expect(within(rowA).getByText(formatDateTime(appA.last_used_at as string))).toBeInTheDocument();
    expect(within(rowA).getByRole('button', { name: 'Revoke Claude' })).toHaveClass('MuiButton-colorError');
    // Dropped columns (DESIGN.md §C6): token counts and expiry never render.
    expect(within(rowA).queryByText(String(appA.active_access_tokens))).not.toBeInTheDocument();

    const rowB = screen.getByTestId('connected-app-adkc_def');
    expect(within(rowB).getByText('Other MCP client')).toBeInTheDocument();
    expect(within(rowB).getAllByText('—')).toHaveLength(1); // last_used_at only
    expect(within(rowB).getByRole('button', { name: 'Revoke Other MCP client' })).toBeInTheDocument();
  });

  it('truncates long client ids to 12 characters in the caption line', async () => {
    global.fetch = vi.fn(async () =>
      jsonResponse({ items: [{ ...appA, client_id: 'adkc_0123456789abcdef' }] }),
    );

    renderScreen();

    expect(await screen.findByText('adkc_0123456')).toBeInTheDocument();
    expect(screen.queryByText('adkc_0123456789abcdef')).not.toBeInTheDocument();
  });

  it('renders the header above the empty state when the list is empty', async () => {
    global.fetch = vi.fn(async () => jsonResponse({ items: [] }));

    renderScreen();

    expect(await screen.findByText('No connected apps')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Connected apps' })).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('shows a labelled table skeleton (not a spinner) while the first load is pending', () => {
    global.fetch = vi.fn(() => new Promise<Response>(() => {}));

    renderScreen();

    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  });
```

(Replace the existing `renders EmptyState when the list is empty` and `renders
LoadingIndicator while the first load is pending` cases with the two above; keep the
`ErrorState … on a 500 first load` and `GET hits /api/v1/oauth/clients` cases as they are.)

**Append to `revoke.test.tsx`** (reuse its existing fetch setup for the successful DELETE):

```tsx
  it('a successful revoke shows an "Access revoked" notice and the confirm button is destructive', async () => {
    let getCalls = 0;
    global.fetch = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async (input, init) => {
        const pathname = pathnameOf(input);
        const method = requestMethod(input, init);

        if (pathname === '/api/v1/oauth/clients' && method === 'GET') {
          getCalls += 1;
          return getCalls === 1 ? jsonResponse(twoAppsFixture) : jsonResponse(oneAppFixture);
        }
        if (pathname === '/api/v1/oauth/clients/adkc_abc' && method === 'DELETE') {
          return new Response(null, { status: 204 });
        }
        return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
      },
    );
    const user = userEvent.setup();

    renderScreen();
    await screen.findByTestId('connected-app-adkc_abc');
    await user.click(screen.getByRole('button', { name: 'Revoke Claude' }));
    const dialog = await screen.findByRole('dialog');
    const confirm = within(dialog).getByRole('button', { name: 'Revoke' });
    expect(confirm).toHaveClass('MuiButton-colorError');
    await user.click(confirm);

    expect(await screen.findByRole('status')).toHaveTextContent('Access revoked');
  });
```

- [ ] **Run RED:** `pnpm -C apps/admin test -- ConnectedApps` → the rewritten/appended cases
  fail (old headers, spinner, no header on empty, gold revoke, no notice); the untouched
  cases stay green.

- [ ] **GREEN — implementer:** copy → hook (snackbar calls) → skeleton → table → screen.

- [ ] **Run GREEN:** `pnpm -C apps/admin test`; `pnpm -C apps/admin type-check`.

- [ ] **Screenshots** (iframe technique, 1440 + 390, real screen, signed in against the local
  API — the local DB has whatever DCR clients exist; if none, capture the empty state and say
  so): `/connected-apps`. Store as `t21-connected-apps-*.jpg`.

- [ ] **Gates:** `pnpm gates:admin` → clean.

- [ ] **Commit:**
  `git add apps/admin/src/components/connectedApps apps/admin/src/lib/copy.ts`
  `git commit -m "feat(admin): connected apps — header, focused table, destructive revoke, refresh feedback (p8 t21)"`

## Verify

```bash
pnpm -C apps/admin test -- ConnectedApps
pnpm gates:admin
```

## Acceptance

- Header + description in every state; table with Client/Connected/Last used/Actions;
  12-char id caption; `formatOptionalDateTime` dashes; red outlined Revoke; destructive confirm.
- "Access revoked" success notice; background refetch failure surfaces via the global snackbar
  (F-5 closed); skeleton while loading.
- `revoke.test.tsx`'s existing four cases pass unchanged.
