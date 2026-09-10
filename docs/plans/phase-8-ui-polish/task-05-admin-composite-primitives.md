---
id: p8-t05
phase: phase-8-ui-polish
depends_on: [p8-t04]
status: pending
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: sonnet
---

# Task 05 — Admin composite primitives: `PageHeader`, `StatCard`, `SnackbarProvider` (apps/admin)

## Goal

Three small composites every sub-phase C screen will use: a `PageHeader` (title + optional
description/meta/actions — every admin screen finally gets a heading), a `StatCard` (label +
value, optionally a link — replaces the duplicated dashboard `sx` blob), and an app-wide
`SnackbarProvider` with a `useSnackbar()` hook so any screen can say "Saved" without owning its
own `AppSnackbar` state. The provider is mounted in `Providers`; no screen changes yet.

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §A3 (`PageHeaderProps`, `StatCardProps`, `SnackbarApi`) and §2.
- `docs/FRONTEND-CONVENTIONS.md` §3, §4, §9.
- `apps/admin/src/components/common/AppSnackbar/{Component.tsx, interface.ts, Component.test.tsx, clickaway.test.tsx}`
  — the per-screen snackbar this provider supersedes (its clickaway rule and role mapping carry over).
- `apps/admin/src/components/common/{Stack,Paper,Box,Typography,Link}/` (task 04 + existing).
- `apps/admin/src/app/providers.tsx` — where the provider mounts.
- `apps/admin/src/components/dashboard/DashboardScreen/Component.test.tsx` lines 1–40 — the
  `<Providers>` test-wrapper precedent.

## Files

**Create**
- `common/PageHeader/{Component.tsx, interface.ts, index.ts, Component.test.tsx}`
- `common/StatCard/{Component.tsx, interface.ts, index.ts, Component.test.tsx}`
- `common/SnackbarProvider/{Component.tsx, interface.ts, context.ts, index.ts, Component.test.tsx}`

**Modify**
- `common/index.ts` — export `PageHeader`, `StatCard`, `SnackbarProvider`, `useSnackbar` (+ types).
- `src/app/providers.tsx` — wrap `children` in `<SnackbarProvider>` inside the Redux provider.

## Interfaces

**Consumes:** `Stack`, `Paper`, `Box`, `Typography`, `Link` from `../<Name>`.

**Produces exactly:**

```ts
// common/PageHeader/interface.ts
import type { ReactNode } from 'react';
export interface PageHeaderProps {
  title: string;
  description?: string;
  /** Right-aligned actions (buttons); they wrap under the title below the sm breakpoint. */
  actions?: ReactNode;
  /** Secondary line under the title — e.g. a status chip and dates (editor, DESIGN.md §C5). */
  meta?: ReactNode;
}

// common/StatCard/interface.ts
export interface StatCardProps {
  label: string;
  value: number | string;
  /** When set, the whole card is a link (dashboard → filtered content list, DESIGN.md §C3). */
  href?: string;
}

// common/SnackbarProvider/interface.ts
import type { ReactNode } from 'react';
export interface SnackbarApi {
  success: (message: string) => void;
  error: (message: string) => void;
}
export interface SnackbarProviderProps {
  children: ReactNode;
}

// common/SnackbarProvider/context.ts
export function useSnackbar(): SnackbarApi; // throws 'useSnackbar must be used inside <SnackbarProvider>' outside the provider
```

**`PageHeader/Component.tsx` — exact:**

```tsx
import { Box } from '../Box';
import { Stack } from '../Stack';
import { Typography } from '../Typography';
import type { PageHeaderProps } from './interface';

// phase-8 task-05 (DESIGN.md §A3): one heading block for every admin screen — the page's <h1>
// (styled at the h2 size: an admin console title, not an article title), an optional one-line
// description, an optional meta line, and the screen's primary actions on the right.
export default function Component({ title, description, actions, meta }: PageHeaderProps) {
  return (
    <Stack
      component="header"
      direction={{ xs: 'column', sm: 'row' }}
      alignItems={{ xs: 'flex-start', sm: 'center' }}
      justifyContent="space-between"
      spacing={2}
      sx={{ mb: 3 }}
    >
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="h2" component="h1">
          {title}
        </Typography>
        {description ? (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {description}
          </Typography>
        ) : null}
        {meta ? <Box sx={{ mt: 1 }}>{meta}</Box> : null}
      </Box>
      {actions ? (
        <Stack direction="row" spacing={1} sx={{ flexShrink: 0 }}>
          {actions}
        </Stack>
      ) : null}
    </Stack>
  );
}
```

**`StatCard/Component.tsx` — exact:**

```tsx
import { Link } from '../Link';
import { Paper } from '../Paper';
import { Typography } from '../Typography';
import type { StatCardProps } from './interface';

// phase-8 task-05 (DESIGN.md §A3/§C3): the dashboard's status/tag counts. Replaces the 7-line sx
// blob duplicated in DashboardScreen and TagCounts (FRONTEND-CONVENTIONS §2: "a style used
// twice becomes a variant or a component"). With `href`, the whole card is one link.
export default function Component({ label, value, href }: StatCardProps) {
  const card = (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        height: '100%',
        ...(href ? { '&:hover': { borderColor: 'primary.main' } } : {}),
      }}
    >
      <Typography variant="body2" color="text.secondary" component="p">
        {label}
      </Typography>
      <Typography variant="h3" component="p" sx={{ mt: 0.5 }}>
        {value}
      </Typography>
    </Paper>
  );

  if (!href) {
    return card;
  }
  return (
    <Link href={href} underline="none" color="inherit" sx={{ display: 'block' }}>
      {card}
    </Link>
  );
}
```

**`SnackbarProvider/context.ts` — exact:**

```ts
'use client';

import { createContext, useContext } from 'react';

import type { SnackbarApi } from './interface';

export const SnackbarContext = createContext<SnackbarApi | null>(null);

// phase-8 task-05: any client component under <Providers> can call
// `useSnackbar().success('Saved')` — docs/FRONTEND-CONVENTIONS.md §9's "friendly snackbar".
export function useSnackbar(): SnackbarApi {
  const api = useContext(SnackbarContext);
  if (api === null) {
    throw new Error('useSnackbar must be used inside <SnackbarProvider>');
  }
  return api;
}
```

**`SnackbarProvider/Component.tsx` — exact:**

```tsx
'use client';

import MuiAlert from '@mui/material/Alert';
import MuiSnackbar from '@mui/material/Snackbar';
import { useCallback, useMemo, useState } from 'react';
import type { SyntheticEvent } from 'react';

import { SnackbarContext } from './context';
import type { SnackbarApi, SnackbarProviderProps } from './interface';

const SUCCESS_AUTO_HIDE_MS = 4000;
const ERROR_AUTO_HIDE_MS = 8000;

interface Notice {
  key: number;
  severity: 'success' | 'error';
  message: string;
}

// phase-8 task-05 (DESIGN.md §A3): ONE snackbar for the whole admin app, driven through context,
// replacing the per-screen `AppSnackbar` state. Rules carried over from AppSnackbar: a click
// elsewhere on the page ('clickaway') never dismisses a notice — only the close button or the
// timeout; 'error' is an assertive live region (role="alert"), 'success' a polite one
// (role="status"). A new notice replaces the current one (new `key` remounts the Snackbar so
// its timer restarts).
export default function Component({ children }: SnackbarProviderProps) {
  const [notice, setNotice] = useState<Notice | null>(null);

  const notify = useCallback((severity: Notice['severity'], message: string) => {
    setNotice({ key: Date.now(), severity, message });
  }, []);

  const api = useMemo<SnackbarApi>(
    () => ({
      success: (message) => notify('success', message),
      error: (message) => notify('error', message),
    }),
    [notify],
  );

  const handleSnackbarClose = (_event: SyntheticEvent | Event, reason: string) => {
    if (reason === 'clickaway') {
      return;
    }
    setNotice(null);
  };

  return (
    <SnackbarContext.Provider value={api}>
      {children}
      {notice ? (
        <MuiSnackbar
          key={notice.key}
          open
          onClose={handleSnackbarClose}
          autoHideDuration={notice.severity === 'error' ? ERROR_AUTO_HIDE_MS : SUCCESS_AUTO_HIDE_MS}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        >
          <MuiAlert
            severity={notice.severity}
            role={notice.severity === 'error' ? 'alert' : 'status'}
            onClose={() => setNotice(null)}
            variant="filled"
            sx={{ width: '100%' }}
          >
            {notice.message}
          </MuiAlert>
        </MuiSnackbar>
      ) : null}
    </SnackbarContext.Provider>
  );
}
```

**`SnackbarProvider/index.ts`:**

```ts
export { default as SnackbarProvider } from './Component';
export { useSnackbar } from './context';
export type { SnackbarApi, SnackbarProviderProps } from './interface';
```

**`providers.tsx`:** `<ReduxProvider store={store}><SnackbarProvider>{children}</SnackbarProvider></ReduxProvider>`
(import `SnackbarProvider` from `@/components/common`).

## Steps (TDD)

- [ ] **RED — test-author.**

  `PageHeader/Component.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { PageHeader } from '.';

describe('PageHeader', () => {
  it('renders the title as the page h1 inside a banner-style header with description, meta, and actions', () => {
    render(
      <PageHeader
        title="Content"
        description="Everything published or in draft."
        meta={<span>Updated today</span>}
        actions={<button type="button">New content</button>}
      />,
    );

    expect(screen.getByRole('heading', { level: 1, name: 'Content' })).toBeInTheDocument();
    expect(screen.getByText('Everything published or in draft.')).toBeInTheDocument();
    expect(screen.getByText('Updated today')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'New content' })).toBeInTheDocument();
  });

  it('renders only the title when nothing else is given', () => {
    render(<PageHeader title="Dashboard" />);

    expect(screen.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument();
    expect(screen.queryByRole('button')).toBeNull();
  });
});
```

  `StatCard/Component.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { StatCard } from '.';

describe('StatCard', () => {
  it('renders the label and value as plain content without href', () => {
    render(<StatCard label="Draft" value={4} />);

    expect(screen.getByText('Draft')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('renders the whole card as one link when href is set', () => {
    render(<StatCard label="Published" value={27} href="/content?status=published" />);

    const link = screen.getByRole('link', { name: /Published/ });
    expect(link).toHaveAttribute('href', '/content?status=published');
    expect(link).toHaveTextContent('27');
  });
});
```

  `SnackbarProvider/Component.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';

import { SnackbarProvider, useSnackbar } from '.';

function Consumer() {
  const snackbar = useSnackbar();
  return (
    <>
      <button type="button" onClick={() => snackbar.success('Saved')}>
        ok
      </button>
      <button type="button" onClick={() => snackbar.error('Could not save')}>
        fail
      </button>
    </>
  );
}

describe('SnackbarProvider / useSnackbar', () => {
  it('shows a polite success notice and an assertive error notice', async () => {
    render(
      <SnackbarProvider>
        <Consumer />
      </SnackbarProvider>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'ok' }));
    expect(screen.getByRole('status')).toHaveTextContent('Saved');

    await userEvent.click(screen.getByRole('button', { name: 'fail' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Could not save');
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('dismisses on the close button but not on a click elsewhere', async () => {
    render(
      <SnackbarProvider>
        <Consumer />
      </SnackbarProvider>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'ok' }));
    await userEvent.click(document.body);
    expect(screen.getByRole('status')).toHaveTextContent('Saved');

    await userEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('throws a clear error when used outside the provider', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    expect(() => render(<Consumer />)).toThrow('useSnackbar must be used inside <SnackbarProvider>');
    consoleError.mockRestore();
  });

  it('is mounted by the app Providers', async () => {
    render(
      <Providers>
        <Consumer />
      </Providers>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'ok' }));
    expect(screen.getByRole('status')).toHaveTextContent('Saved');
  });
});
```

- [ ] **Run RED:** `pnpm -C apps/admin test -- PageHeader StatCard SnackbarProvider`
  Expected: FAIL — modules not found.

- [ ] **GREEN — implementer:** the three folders per the Interfaces block → barrel → `providers.tsx`.

- [ ] **Run GREEN:** same command → PASS. `pnpm -C apps/admin type-check` → clean.

- [ ] **Full suite:** `pnpm -C apps/admin test` → green (every screen test already renders
  `<Providers>`, so the new provider is exercised by all of them).

- [ ] **Screenshot:** none required (no screen consumes these yet) — the reviewer confirms the
  diff is limited to `common/**` + `providers.tsx`.

- [ ] **Gates:** `pnpm gates:admin` → clean.

- [ ] **Commit:**
  `git add apps/admin/src/components/common apps/admin/src/app/providers.tsx`
  `git commit -m "feat(admin): PageHeader, StatCard, app-wide SnackbarProvider + useSnackbar (p8 t05)"`

## Verify

```bash
pnpm -C apps/admin test -- PageHeader StatCard SnackbarProvider
pnpm gates:admin
```

## Acceptance

- All three test files pass; full suite green; type-check clean.
- `useSnackbar` is the only way screens will notify from sub-phase C on; `AppSnackbar` stays
  until its last call site migrates (C5), then is deleted there.
- `PageHeader` renders exactly one `<h1>`; `StatCard` with `href` is one link with the value in
  its name/content.
- Reviewer (Sonnet) checks the five dimensions with file:line evidence.
