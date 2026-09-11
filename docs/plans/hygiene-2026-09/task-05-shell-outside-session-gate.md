---
id: hy-t05
phase: hygiene-2026-09
depends_on: []
status: todo
spec: docs/plans/hygiene-2026-09/00-INDEX.md
review: opus
---

# Task 05 — `(app)` layout: `AppShell` outside, `RequireSession` inside

## Goal

Close FINAL(C) X4 (Opus): "RequireSession spinner precedes every skeleton outside the shell
(layout inversion)". `apps/admin/src/app/(app)/layout.tsx` nests `<RequireSession><AppShell>…`
— so on every hard load / refresh the user sees a bare centred spinner on a blank page while
`GET /auth/me` resolves, and only then does the AppBar/drawer paint. Invert it:
`<AppShell><RequireSession>{children}</RequireSession></AppShell>`. The shell chrome paints
immediately; the session spinner, the 401 redirect and the "couldn't verify your session"
error state all render **inside `<main>`**, where the page will be. Next's `(app)/loading.tsx`
and every page skeleton now also mount inside the shell.

**Plan-time ruling (accepted trade-off):** a signed-out visitor to an `(app)` URL sees the
empty shell chrome (wordmark, nav, Agent button; no account menu because `me` is undefined)
for the instant before `router.replace('/signin')` fires. Nothing sensitive is in the chrome.

## Context (read ONLY these)

- `apps/admin/src/app/(app)/layout.tsx` (13 lines), `apps/admin/src/app/(app)/loading.tsx`
- `apps/admin/src/components/auth/RequireSession/{Component.tsx, Component.test.tsx}` — the
  guard's three states (loading → `LoadingIndicator`; 401 → `router.replace('/signin')` and
  `null`; other error → `ErrorState`; data → children). **Unchanged by this task.**
- `apps/admin/src/components/shell/AppShell/{Component.tsx, Component.test.tsx}` — the frame;
  its own `useGetMeQuery()` only feeds the account menu (renders nothing while `me` is
  undefined). **Unchanged by this task.** Copy this test file's `mockFetch`/`jsonResponse`/
  `requestUrl` helpers and its `vi.mock('next/navigation', () => import('@/testing/nextNavigation'))`
  seam for the new layout test.
- `apps/admin/src/app/not-found.test.tsx` — the shape of an `app/` route test.
- `apps/admin/src/testing/nextNavigation.ts` — `navigation.reset(href)`, `navigation.replace` spy.
- `docs/FRONTEND-CONVENTIONS.md` §3 (pages/layouts thin), §7, §9.

## Files

**Create**
- `apps/admin/src/app/(app)/layout.test.tsx`

**Modify**
- `apps/admin/src/app/(app)/layout.tsx`

## Interfaces

```tsx
// apps/admin/src/app/(app)/layout.tsx — after
import type { ReactNode } from 'react';

import { RequireSession } from '@/components/auth/RequireSession';
import { AppShell } from '@/components/shell/AppShell';

// task-04: this route group owns every authenticated admin page — nested under RootLayout's
// Providers. hygiene t05 (p8 final X4): the shell now wraps the session gate, not the other
// way round — the AppBar/drawer paint immediately and the session spinner / 401 redirect /
// error state render inside <main>, where the page will be, instead of on a blank page.
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <AppShell>
      <RequireSession>{children}</RequireSession>
    </AppShell>
  );
}
```

## Steps

- [ ] **Step 1 (test-author, RED): create `apps/admin/src/app/(app)/layout.test.tsx`.**

  ```tsx
  // @vitest-environment jsdom
  import { render, screen, waitFor, within } from '@testing-library/react';
  import '@testing-library/jest-dom/vitest';
  import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

  import Providers from '@/app/providers';
  import { navigation } from '@/testing/nextNavigation';

  import Layout from './layout';

  // hygiene t05 (p8 final X4): the authenticated layout paints the shell chrome BEFORE the
  // session query resolves; the gate's loading / redirect / error states live inside <main>.
  // Mock ONLY fetch and the next/navigation seam (docs/FRONTEND-CONVENTIONS.md §7).
  vi.mock('next/navigation', () => import('@/testing/nextNavigation'));

  const meFixture = {
    id: '11111111-1111-1111-1111-111111111111',
    email: 'ada@advisordesk.test',
    name: 'Ada Lovelace',
    avatar_url: null,
  };

  function jsonResponse(body: unknown, status = 200): Response {
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  function requestUrl(input: RequestInfo | URL): string {
    return input instanceof Request ? input.url : String(input);
  }

  function mockMe(respond: () => Promise<Response>) {
    global.fetch = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async (input) => {
        if (requestUrl(input).includes('/auth/me')) return respond();
        return jsonResponse({}, 404);
      },
    );
  }

  function renderLayout() {
    return render(
      <Providers>
        <Layout>
          <div>Page body</div>
        </Layout>
      </Providers>,
    );
  }

  function expectShellChrome() {
    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'AdvisorDesk Admin' })).toHaveAttribute('href', '/');
  }

  describe('(app) layout', () => {
    beforeEach(() => {
      navigation.reset('/');
    });

    afterEach(() => {
      vi.restoreAllMocks();
    });

    it('renders the shell chrome and a loading indicator inside main while /auth/me is pending — not the page', () => {
      mockMe(() => new Promise<Response>(() => {}));

      renderLayout();

      expectShellChrome();
      const main = screen.getByRole('main');
      expect(within(main).getByRole('progressbar')).toBeInTheDocument();
      expect(screen.queryByText('Page body')).not.toBeInTheDocument();
      expect(navigation.replace).not.toHaveBeenCalled();
    });

    it('keeps the shell chrome and redirects to /signin on a 401, never rendering the page', async () => {
      mockMe(async () =>
        jsonResponse({ error: { code: 'unauthorized', message: 'Authentication required.' } }, 401),
      );

      renderLayout();

      await waitFor(() => {
        expect(navigation.replace).toHaveBeenCalledWith('/signin');
      });
      expectShellChrome();
      expect(screen.queryByText('Page body')).not.toBeInTheDocument();
    });

    it('renders a session error state inside main (shell still up) when /auth/me fails for another reason', async () => {
      mockMe(async () => jsonResponse({ error: { code: 'internal', message: 'boom' } }, 500));

      renderLayout();

      const main = screen.getByRole('main');
      expect(
        await within(main).findByText("Couldn't verify your session. Please try again."),
      ).toBeInTheDocument();
      expectShellChrome();
      expect(navigation.replace).not.toHaveBeenCalled();
      expect(screen.queryByText('Page body')).not.toBeInTheDocument();
    });

    it('renders the page inside main once /auth/me succeeds, with the account menu in the bar', async () => {
      mockMe(async () => jsonResponse(meFixture, 200));

      renderLayout();

      const main = screen.getByRole('main');
      expect(await within(main).findByText('Page body')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Ada Lovelace/ })).toBeInTheDocument();
      expect(navigation.replace).not.toHaveBeenCalled();
    });
  });
  ```

  If `LoadingIndicator` does not render a `progressbar` role (check
  `apps/admin/src/components/common/LoadingIndicator/Component.tsx`), query it the way its own
  test does and note the substitution in the report.

- [ ] **Step 2: run RED.** `cd apps/admin && npx vitest run "src/app/(app)/layout"` → all four
  tests fail (no `banner`/`main` on the first render while the shell sits inside the gate — the
  fourth test's `getByRole('main')` is synchronous, so it fails too). Paste the failure lines.
  *(Corrected during execution: the original text predicted 3 of 4.)*

- [ ] **Step 3 (implementer, GREEN):** replace `layout.tsx` with the Interfaces version.

- [ ] **Step 4: run GREEN + gates.** `npx vitest run "src/app/(app)/layout" RequireSession
  AppShell`, then the full `npx vitest run`, `pnpm -C apps/admin type-check`, `lint`,
  `format:check`, and **`pnpm -C apps/admin build`** (the layout is a Server Component that
  renders two client components — the build must stay green).

- [ ] **Step 5: screenshot (visible change).** Start `pnpm -C apps/admin dev` with the API
  **not** running (so `/auth/me` fails with a network error) and capture
  `http://localhost:3001/content` at 1440 px wide: the AppBar + drawer must be visible with
  the "Couldn't verify your session" error state inside the main area. Save as
  `.superpowers/sdd/hygiene-2026-09/screenshots/t05-shell-with-session-error-1440.png` (jpg
  is fine). Before this task the same URL showed a bare spinner/error on a blank page — say so
  in the report.

- [ ] **Step 6: commit.** `git commit -m "refactor(admin): paint AppShell before the session gate resolves (p8 final X4)"`

## Acceptance criteria

- `layout.tsx` is exactly the Interfaces version (modulo Prettier).
- The four new tests pass; `RequireSession` and `AppShell` test files are untouched.
- `next build` green; screenshot shows the shell chrome around the session error state.

## Report

Test-author → `.superpowers/sdd/hygiene-2026-09/reports/task-05-test-author.md`;
implementer → `.superpowers/sdd/hygiene-2026-09/reports/task-05-implementer.md` (include the
build tail and the screenshot path).
