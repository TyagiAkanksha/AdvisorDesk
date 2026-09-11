---
id: p8-t15
phase: phase-8-ui-polish
depends_on: [p8-t14]
status: pending
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: sonnet
---

# Task 15 — Admin shell: responsive nav drawer, active nav, single `<main>` (C1)

## Goal

The admin frame becomes a conventional responsive console shell: a wordmark, a menu button
that opens a temporary nav drawer below `md` (permanent 240px drawer at `md`+), nav items with
icons and a highlighted current route, an outlined "Agent" button with an icon, the account
menu extracted into a leaf, ONE `<main>` landmark padded once by the shell, and an agent drawer
that is 400px wide on desktop and full-width on phones. Layout state moves into a colocated
`useAppShell` hook.

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §2 and §5 C1.
- `docs/FRONTEND-CONVENTIONS.md` §3 (VM hooks colocated; leaf components under
  `<Parent>/components/`), §7, §9.
- `apps/admin/src/components/shell/AppShell/{Component.tsx, interface.ts, Component.test.tsx,
  agentPanelToggle.test.tsx, ariaTriggers.test.tsx}` — the current shell and its pins (the
  three test files switch to the task-14 navigation seam; every existing assertion is kept).
- `apps/admin/src/components/common/{AppBar,Drawer,NavList,IconButton,Button,Link,Icon,Menu,Avatar,Box,ToolbarSpacer,PageContainer}/`
  and `common/useBreakpointDown/` (task 14), `common/index.ts`.
- `apps/admin/src/testing/{nextNavigation.ts, matchMedia.ts}` (task 14).
- `apps/admin/src/app/not-found.tsx` + `not-found.test.tsx`; `apps/admin/src/app/(app)/*.tsx`
  (pages wrap screens in `PageContainer` — unchanged call sites).
- `apps/admin/src/lib/copy.ts`.

## Files

**Create**
- `src/lib/navigation.ts`, `src/lib/navigation.test.ts`
- `src/components/shell/AppShell/useAppShell.ts`, `src/components/shell/AppShell/useAppShell.test.tsx`
- `src/components/shell/AppShell/components/AccountMenu/{Component.tsx, interface.ts, index.ts}`
- `src/components/shell/AppShell/responsiveNav.test.tsx`

**Modify**
- `src/components/shell/AppShell/Component.tsx`
- `src/components/shell/AppShell/{Component,agentPanelToggle,ariaTriggers}.test.tsx` (mock →
  seam; new cases appended to `Component.test.tsx`)
- `src/components/common/PageContainer/Component.tsx`
- `src/app/not-found.tsx` (+ one case in `not-found.test.tsx`)
- `src/lib/copy.ts`

## Interfaces

```ts
// src/lib/navigation.ts — pure. '/' matches only itself; every other href matches itself or
// `${href}/…` (a real path segment boundary — '/content-archive' does NOT activate '/content';
// closes the task-08 minor carried from sub-phase B).
export function isActivePath(pathname: string, href: string): boolean;

// src/components/shell/AppShell/useAppShell.ts
export interface UseAppShellResult {
  /** Below the `md` breakpoint (`useBreakpointDown('md')`). */
  isNarrow: boolean;
  /** Temporary nav drawer state — only meaningful while `isNarrow`. */
  navOpen: boolean;
  openNav: () => void;
  closeNav: () => void;
  agentOpen: boolean;
  toggleAgent: () => void;
  closeAgent: () => void;
  /** The three routes with icons and `selected` computed from `usePathname()`. */
  navItems: NavListItem[];
}
export function useAppShell(): UseAppShellResult;
// NAV_ITEMS (module const): { label: DASHBOARD_TITLE, href: '/', icon: 'Dashboard' },
//   { label: CONTENT_TITLE, href: '/content', icon: 'Article' },
//   { label: CONNECTED_APPS_TITLE, href: '/connected-apps', icon: 'Link' }

// components/AccountMenu/interface.ts — the avatar button + "Sign out" menu, moved out of
// AppShell verbatim (anchor element state stays inside this leaf: it is presentational).
export interface AccountMenuProps {
  name: string;            // `me.name ?? me.email`
  avatarUrl: string | null;
  onSignOut: () => void;
}

// src/lib/copy.ts additions
// One constant per section — the nav label IS the page title (tasks 17/18/21 reuse these as
// their PageHeader titles; do not add DASHBOARD_TITLE-style duplicates).
export const DASHBOARD_TITLE = 'Dashboard';
export const CONTENT_TITLE = 'Content';
export const CONNECTED_APPS_TITLE = 'Connected apps';
export const MAIN_NAV_LABEL = 'Main';
export const OPEN_NAVIGATION_LABEL = 'Open navigation';
export const AGENT_BUTTON_LABEL = 'Agent';
export const SIGN_OUT_LABEL = 'Sign out';
```

**AppShell render (exact structure):**

```tsx
<Box sx={{ display: 'flex', minHeight: '100vh' }}>
  <AppBar>
    {shell.isNarrow ? (
      <IconButton name="Menu" label={OPEN_NAVIGATION_LABEL} onClick={shell.openNav} color="inherit" edge="start" />
    ) : null}
    <Link href="/" variant="h6" underline="none" color="inherit" sx={{ mr: 3 }}>
      {APP_NAME}
    </Link>
    <Box sx={{ flexGrow: 1 }} />
    <Button
      variant="outlined"
      color="inherit"
      startIcon={<Icon name="SmartToy" />}
      aria-haspopup="true"
      aria-expanded={shell.agentOpen}
      aria-controls="app-shell-agent-panel"
      onClick={shell.toggleAgent}
    >
      {AGENT_BUTTON_LABEL}
    </Button>
    {me ? <AccountMenu name={me.name ?? me.email} avatarUrl={me.avatar_url} onSignOut={handleSignOut} /> : null}
  </AppBar>
  <Drawer
    variant={shell.isNarrow ? 'temporary' : 'permanent'}
    open={shell.isNarrow ? shell.navOpen : true}
    onClose={shell.closeNav}
  >
    <Box component="nav" aria-label={MAIN_NAV_LABEL}>
      <NavList items={shell.navItems} onNavigate={shell.closeNav} />
    </Box>
  </Drawer>
  <Box component="main" sx={{ flexGrow: 1, minWidth: 0, p: { xs: 2, md: 3 } }}>
    <ToolbarSpacer />
    {children}
  </Box>
  <Drawer
    id="app-shell-agent-panel"
    anchor="right"
    variant="persistent"
    open={shell.agentOpen}
    width={shell.isNarrow ? '100vw' : 400}
  >
    <AgentPanel />
  </Drawer>
</Box>
```

`useGetMeQuery`/`useLogoutMutation`/`useRouter` + `handleSignOut` stay in `AppShell`
(unchanged). The agent drawer's `onClose` is REMOVED — a persistent drawer never fires it (the
phase-6 "dead Drawer onClose" backlog item); the panel's own close button (task 23) and the
AppBar toggle are the close paths, so the `agentOpen`/`closeAgent` state is what they call.
`AccountMenu` keeps the exact aria/avatar behaviour of today's block (WR-13/WR-66 comments move
with it; `aria-controls` only while open; `Avatar alt="" aria-hidden`; menu id
`app-shell-account-menu`; option label `SIGN_OUT_LABEL`).

**`PageContainer` becomes:** `<Container maxWidth="lg">{children}</Container>` — no
`component="main"`, no `py` (the shell pads once). **`not-found.tsx`** wraps its
`PageContainer` in `<Box component="main" sx={{ py: 4 }}>` so the unframed 404 keeps a main
landmark.

## Steps (TDD)

- [ ] **RED — test-author.**

**`src/lib/navigation.test.ts`** (node)

```ts
import { describe, expect, it } from 'vitest';

import { isActivePath } from './navigation';

describe('isActivePath', () => {
  it.each([
    ['/', '/', true],
    ['/content', '/', false],
    ['/content', '/content', true],
    ['/content/new', '/content', true],
    ['/content/11111111-1111-1111-1111-111111111111', '/content', true],
    ['/content-archive', '/content', false],
    ['/connected-apps', '/connected-apps', true],
    ['/connected-apps', '/content', false],
  ])('isActivePath(%s, %s) → %s', (pathname, href, expected) => {
    expect(isActivePath(pathname, href)).toBe(expected);
  });
});
```

**`src/components/shell/AppShell/useAppShell.test.tsx`**

```tsx
// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { stubMatchMedia } from '@/testing/matchMedia';
import { navigation } from '@/testing/nextNavigation';

import { useAppShell } from './useAppShell';

vi.mock('next/navigation', () => import('@/testing/nextNavigation'));

describe('useAppShell', () => {
  let restore: (() => void) | null = null;

  beforeEach(() => {
    navigation.reset('/content/11111111-1111-1111-1111-111111111111');
  });

  afterEach(() => {
    restore?.();
    restore = null;
  });

  it('selects the nav item whose route contains the pathname, and gives every item an icon', () => {
    const { result } = renderHook(() => useAppShell());

    expect(result.current.navItems.map((item) => [item.href, item.selected])).toEqual([
      ['/', false],
      ['/content', true],
      ['/connected-apps', false],
    ]);
    expect(result.current.navItems.every((item) => item.icon !== undefined)).toBe(true);
  });

  it('selects Dashboard only on the exact root path', () => {
    navigation.reset('/');

    const { result } = renderHook(() => useAppShell());

    expect(result.current.navItems.map((item) => item.selected)).toEqual([true, false, false]);
  });

  it('starts desktop-wide with both drawers closed', () => {
    const { result } = renderHook(() => useAppShell());

    expect(result.current.isNarrow).toBe(false);
    expect(result.current.navOpen).toBe(false);
    expect(result.current.agentOpen).toBe(false);
  });

  it('below md, openNav/closeNav toggle the temporary nav drawer', () => {
    restore = stubMatchMedia(true);
    const { result } = renderHook(() => useAppShell());

    expect(result.current.isNarrow).toBe(true);
    act(() => result.current.openNav());
    expect(result.current.navOpen).toBe(true);
    act(() => result.current.closeNav());
    expect(result.current.navOpen).toBe(false);
  });

  it('toggleAgent flips the agent panel; closeAgent forces it closed', () => {
    const { result } = renderHook(() => useAppShell());

    act(() => result.current.toggleAgent());
    expect(result.current.agentOpen).toBe(true);
    act(() => result.current.toggleAgent());
    expect(result.current.agentOpen).toBe(false);
    act(() => result.current.toggleAgent());
    act(() => result.current.closeAgent());
    expect(result.current.agentOpen).toBe(false);
  });
});
```

**Migrate the three existing AppShell test files** — replace the `replaceMock`/`pushMock` +
static `vi.mock('next/navigation', …)` block with:

```tsx
import { navigation } from '@/testing/nextNavigation';

vi.mock('next/navigation', () => import('@/testing/nextNavigation'));
```

and in EACH of the three files add `beforeEach(() => { navigation.reset('/'); })` inside the
`describe` (in `Component.test.tsx` this replaces the `mockClear` lines) — every shell test
starts from a known URL, and the import is used in all three files (zero lint warnings). The sign-out redirect assertion becomes:

```tsx
    await waitFor(() => {
      const redirectedToSignin =
        navigation.replace.mock.calls.some(([to]) => to === '/signin') ||
        navigation.push.mock.calls.some(([to]) => to === '/signin');
      expect(redirectedToSignin).toBe(true);
    });
```

Every other assertion in the three files stays byte-identical. **Append to
`Component.test.tsx`**:

```tsx
  it('renders exactly one main landmark and the "Main" navigation landmark', async () => {
    mockFetch();

    renderShell();
    await screen.findByText('Dashboard body');

    expect(screen.getAllByRole('main')).toHaveLength(1);
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument();
  });

  it('marks the current route\'s nav link with aria-current="page" and no other', async () => {
    navigation.reset('/connected-apps');
    mockFetch();

    renderShell();
    await screen.findByText('Dashboard body');

    expect(screen.getByRole('link', { name: 'Connected apps' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('link', { name: 'Content' })).not.toHaveAttribute('aria-current');
    expect(screen.getByRole('link', { name: 'Dashboard' })).not.toHaveAttribute('aria-current');
  });

  it('renders the wordmark as a link to / and no menu button at desktop width', async () => {
    mockFetch();

    renderShell();
    await screen.findByText('Dashboard body');

    expect(screen.getByRole('link', { name: 'AdvisorDesk Admin' })).toHaveAttribute('href', '/');
    expect(screen.queryByRole('button', { name: 'Open navigation' })).not.toBeInTheDocument();
  });
```

**`src/components/shell/AppShell/responsiveNav.test.tsx`** (new one-behaviour file; copy the
`meFixture`/`jsonResponse`/`requestUrl`/`mockFetch`/`renderShell` helpers from
`Component.test.tsx` verbatim)

```tsx
// @vitest-environment jsdom
import { render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import { stubMatchMedia } from '@/testing/matchMedia';
import { navigation } from '@/testing/nextNavigation';

import { AppShell } from '.';

vi.mock('next/navigation', () => import('@/testing/nextNavigation'));

// … meFixture, jsonResponse, requestUrl, mockFetch, renderShell exactly as in Component.test.tsx …

describe('AppShell below the md breakpoint', () => {
  let restore: (() => void) | null = null;

  beforeEach(() => {
    navigation.reset('/');
    restore = stubMatchMedia(true);
  });

  afterEach(() => {
    restore?.();
    restore = null;
    vi.restoreAllMocks();
  });

  it('hides the nav behind an "Open navigation" button; it opens on click and closes after navigating', async () => {
    mockFetch();
    const user = userEvent.setup();

    renderShell();
    await screen.findByText('Dashboard body');

    // Closed temporary drawer is `visibility: hidden` (MUI keepMounted) — excluded from role queries.
    expect(screen.queryByRole('navigation', { name: 'Main' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Open navigation' }));
    const nav = await screen.findByRole('navigation', { name: 'Main' });
    expect(within(nav).getByRole('link', { name: 'Content' })).toBeInTheDocument();

    await user.click(within(nav).getByRole('link', { name: 'Content' }));

    await waitFor(() =>
      expect(screen.queryByRole('navigation', { name: 'Main' })).not.toBeInTheDocument(),
    );
  });

  it('the agent drawer is full-width on phones', async () => {
    mockFetch();
    const user = userEvent.setup();

    renderShell();
    await screen.findByText('Dashboard body');
    await user.click(screen.getByRole('button', { name: 'Agent' }));

    const panel = document.getElementById('app-shell-agent-panel');
    expect(panel).not.toBeNull();
    // jsdom resolves `100vw` to pixels (sub-phase A lesson) — assert the paper is as wide as the
    // viewport rather than pinning the unit.
    const paper = panel!.querySelector('.MuiDrawer-paper');
    expect(paper).toHaveStyle({ width: `${window.innerWidth}px` });
  });
});
```

**Append to `src/app/not-found.test.tsx`**:

```tsx
  it('keeps a main landmark of its own (it renders outside AppShell)', () => {
    render(<NotFound />);

    expect(screen.getByRole('main')).toBeInTheDocument();
  });
```

- [ ] **Run RED:** `pnpm -C apps/admin test -- AppShell navigation not-found` → `useAppShell`/
  `lib/navigation` unresolved; the appended `Component.test.tsx` cases fail (no `nav`
  landmark, no wordmark link, no `aria-current`; the single-`main` assertion alone passes
  today); `responsiveNav` fails (no menu button, agent drawer 400px). The not-found `main`
  case is GREEN today (PageContainer still renders `main`) and must STAY green after
  PageContainer loses it — it is a regression guard, say so in the report.

- [ ] **GREEN — implementer:** `lib/navigation.ts` → `useAppShell.ts` → `AccountMenu` leaf →
  `AppShell/Component.tsx` per Interfaces → `PageContainer` → `not-found.tsx` → copy. Keep
  `AgentPanel` mounted unconditionally (conversation state survives, phase-5 rule).

- [ ] **Run GREEN:** `pnpm -C apps/admin test`; `pnpm -C apps/admin type-check`.

- [ ] **Screenshots** (iframe technique, 1440 + 390; `NEXT_PUBLIC_API_URL` pointing at the
  local API is fine — sign in is not required for the shell frame to render: capture
  `/signin` is NOT the target; render the shell through a throwaway route under `(app)` that
  bypasses `RequireSession`, e.g. `src/app/(app)/__shell/page.tsx` rendering
  `<AppShell><PageSkeleton/></AppShell>` directly, deleted before commit): desktop = permanent
  drawer with icons + selected row, wordmark, outlined Agent button; phone = menu button, no
  drawer, then the open temporary drawer; agent drawer open at both widths. Store under
  `.superpowers/sdd/phase-8-ui-polish/screenshots/t15-*.jpg`.

- [ ] **Gates:** `pnpm gates:admin` → clean; `pnpm -C apps/admin build` → exit 0 (throwaway
  route removed first — verify `git status` shows no `__shell`).

- [ ] **Commit:**
  `git add apps/admin/src/components/shell apps/admin/src/components/common/PageContainer apps/admin/src/app/not-found.tsx apps/admin/src/app/not-found.test.tsx apps/admin/src/lib/navigation.ts apps/admin/src/lib/navigation.test.ts apps/admin/src/lib/copy.ts`
  `git commit -m "feat(admin): responsive app shell — temporary nav drawer, active nav, single main (p8 t15)"`

## Verify

```bash
pnpm -C apps/admin test -- AppShell navigation not-found
pnpm gates:admin && pnpm -C apps/admin build
```

## Acceptance

- One `<main>` per page; `nav[aria-label="Main"]` with icons and `aria-current="page"` on the
  active route (`isActivePath` semantics); wordmark links to `/`.
- Below `md`: "Open navigation" button, temporary drawer that closes on navigation; agent
  drawer full-width. At `md`+: permanent 240px drawer, no menu button; agent drawer 400px.
- All prior AppShell pins green through the navigation seam; screenshots at both widths.
