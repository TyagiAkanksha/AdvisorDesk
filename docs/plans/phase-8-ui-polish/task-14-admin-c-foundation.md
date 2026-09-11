---
id: p8-t14
phase: phase-8-ui-polish
depends_on: []
status: done
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: sonnet
---

# Task 14 — Admin sub-phase C foundation: test seams, `useBreakpointDown`, `lib/format`, primitive extensions

## Goal

Everything tasks 15–23 share, in one reviewable batch: two test seams the admin app lacks
(a stateful `next/navigation` mock so URL-driven screens re-render when they write the URL, and a
`matchMedia` stub so responsive branches can be tested), the one MUI-importing hook the
responsive shell and editor need (`useBreakpointDown`), the app's date formatters, three
pass-through primitives (`Grid`, `Chip`, `CircularProgress`), five icon registrations, and
small extensions to `EmptyState`, `IconButton`, `TextField`, `Autocomplete`. No screen changes.

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §2, §5 (C1 `useMediaQuery`, C4 `lib/format.ts`,
  C4/C7 `EmptyState` actions, C5 monospace body + tag options, C7 icons), §6 (matchMedia
  mocking).
- `docs/FRONTEND-CONVENTIONS.md` §3 (folder-per-component; hooks), §4 (MUI only under
  `common/`), §7.
- `apps/admin/eslint.config.mjs` lines 15–30 — the boundary `ignores` list (`src/components/
  common/**` is allowed to import `@mui/*`; `src/lib/**` and `src/testing/**` are NOT).
- `apps/admin/src/components/common/{EmptyState,IconButton,TextField,Autocomplete,Icon,Button}/`
  — the files extended here; `common/Button/Component.tsx` is the `isInternalHref` + `'use
  client'` precedent `IconButton` copies.
- `apps/admin/src/components/common/index.ts` (barrel), `apps/admin/src/lib/copy.ts`.
- `apps/client/src/components/common/{Grid,Chip,CircularProgress}/` — copy these three
  pass-throughs verbatim (interface comments adjusted to say `apps/admin`).
- `apps/admin/vitest.config.ts`, `apps/admin/vitest.setup.ts` — `globals: false`, jsdom via
  pragma, RTL cleanup + store reset per test.
- `apps/admin/src/components/shell/AppShell/Component.test.tsx` lines 12–20 — the static
  `vi.mock('next/navigation', …)` idiom this task's seam replaces for URL-driven screens.

## Files

**Create**
- `src/testing/nextNavigation.ts`, `src/testing/nextNavigation.test.tsx`
- `src/testing/matchMedia.ts`
- `src/components/common/useBreakpointDown/{useBreakpointDown.ts, index.ts, useBreakpointDown.test.tsx}`
- `src/lib/format.ts`, `src/lib/format.test.ts`
- `src/components/common/Grid/{Component.tsx, interface.ts, index.ts}`
- `src/components/common/Chip/{Component.tsx, interface.ts, index.ts}`
- `src/components/common/CircularProgress/{Component.tsx, interface.ts, index.ts}`
- `src/components/common/EmptyState/Component.test.tsx`
- `src/components/common/IconButton/Component.test.tsx`

**Modify**
- `src/components/common/index.ts` (export `Grid`, `Chip`, `CircularProgress`, `useBreakpointDown`)
- `src/components/common/EmptyState/{Component.tsx, interface.ts}`
- `src/components/common/IconButton/{Component.tsx, interface.ts}`
- `src/components/common/TextField/{Component.tsx, interface.ts}` (+ append to `Component.test.tsx`)
- `src/components/common/Autocomplete/{Component.tsx, interface.ts}` (+ new `Component.test.tsx`)
- `src/components/common/Icon/Component.tsx` (+ append to `Component.test.tsx`)
- `src/lib/copy.ts` (+ append to `copy.test.ts`)

## Interfaces

**Produces (consumed by tasks 15–23):**

```ts
// src/testing/nextNavigation.ts — a stand-in for `next/navigation` with ONE module-level
// location that `useRouter().replace/push` write and `usePathname`/`useSearchParams` subscribe to
// (via `useSyncExternalStore`), so components re-render on every write exactly as they do under
// the real App Router. Usage in a test file:
//   vi.mock('next/navigation', () => import('@/testing/nextNavigation'));
//   import { navigation } from '@/testing/nextNavigation';
//   beforeEach(() => navigation.reset('/content?status=draft'));
export const navigation: {
  replace: Mock<(href: string, options?: { scroll?: boolean }) => void>;
  push: Mock<(href: string, options?: { scroll?: boolean }) => void>;
  /** Set the mocked URL and clear both spies — call in `beforeEach`. Default `'/'`. */
  reset: (href?: string) => void;
  readonly pathname: string;
  readonly search: string; // '' or '?a=b'
};
export function useRouter(): { replace; push; back; forward; refresh; prefetch }; // the last four are inert vi.fn()s
export function usePathname(): string;
export function useSearchParams(): URLSearchParams; // a fresh instance per render, built from the subscribed `search`

// src/testing/matchMedia.ts — jsdom has no `window.matchMedia`, so MUI's `useMediaQuery`
// always reports `false` there. This installs a stub that reports `matches` for EVERY query and
// returns a restore function (call it in `afterEach`).
export function stubMatchMedia(matches: boolean): () => void;

// src/components/common/useBreakpointDown/useBreakpointDown.ts — the ONLY `useMediaQuery` import
export function useBreakpointDown(key: 'sm' | 'md' | 'lg'): boolean; // true below the breakpoint

// src/lib/format.ts — `Intl.DateTimeFormat('en-US', …)`, viewer's local time zone (admin screens
// render client-side only: RequireSession shows a spinner during SSR, so there is no hydration
// mismatch to guard against, unlike apps/client's UTC-pinned formatDate)
export function formatDate(iso: string): string;            // { dateStyle: 'medium' } → "Mar 15, 2026"
export function formatDateTime(iso: string): string;        // { dateStyle: 'medium', timeStyle: 'short' } → "Mar 15, 2026, 12:00 PM"
export function formatOptionalDateTime(iso: string | null): string; // null → PLACEHOLDER_DASH

// common/EmptyState/interface.ts (additions)
icon?: IconProps['name'];   // default 'Article'
action?: ReactNode;         // rendered under the text inside `<Box sx={{ mt: 2 }}>`

// common/IconButton/interface.ts — `onClick` becomes optional; three props added:
href?: string;              // internal → `MuiIconButton component={Link} href` (next/link), else plain `href`; file gains 'use client'
color?: 'default' | 'inherit' | 'primary' | 'error'; // default 'default'; 'inherit' for buttons on the navy AppBar
edge?: 'start' | 'end';     // MUI's toolbar edge alignment (the AppBar menu button uses 'start')
tooltip?: string;           // wraps the MuiIconButton in `<MuiTooltip title={tooltip}>` (inside this primitive — MUI's Tooltip
                            // clones its child with hover handlers + a ref, which a closed wrapper cannot forward, so the
                            // tooltip has to live here). The `label` stays the accessible name (child props win in Tooltip).

// common/TextField/interface.ts (addition)
monospace?: boolean;        // sx `{ '& .MuiInputBase-input': { fontFamily: 'monospace' } }`

// common/Autocomplete/interface.ts (addition)
options?: string[];         // suggestions shown in the popup; default `[]` (freeSolo stays on)

// common/Icon/Component.tsx registry additions (named imports from @mui/icons-material):
SmartToy, Link, ExpandMore, Send, Stop

// common/index.ts additions
export { Grid } / GridProps; export { Chip } / ChipProps; export { CircularProgress } / CircularProgressProps;
export { useBreakpointDown } from './useBreakpointDown';

// src/lib/copy.ts addition
export const APP_NAME = 'AdvisorDesk Admin';
```

**`nextNavigation.ts` implementation (exact):**

```ts
import { useSyncExternalStore } from 'react';
import { vi } from 'vitest';

// phase-8 task-14: a stateful stand-in for `next/navigation` for tests of screens that keep
// their state in the URL (DESIGN.md §C4). A static `vi.fn()` router cannot re-render the
// component that called `replace()`; this module holds ONE location that the router methods
// write and the two read hooks subscribe to, so tests exercise the real "write URL → re-render
// from URL" loop.
interface Location {
  pathname: string;
  search: string;
}

let location: Location = { pathname: '/', search: '' };
const listeners = new Set<() => void>();

function setLocation(href: string): void {
  const url = new URL(href, 'http://admin.test');
  location = { pathname: url.pathname, search: url.search };
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

const replace = vi.fn((href: string, _options?: { scroll?: boolean }) => setLocation(href));
const push = vi.fn((href: string, _options?: { scroll?: boolean }) => setLocation(href));

export const navigation = {
  replace,
  push,
  reset(href = '/'): void {
    replace.mockClear();
    push.mockClear();
    setLocation(href);
  },
  get pathname(): string {
    return location.pathname;
  },
  get search(): string {
    return location.search;
  },
};

export function useRouter() {
  return { replace, push, back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() };
}

export function usePathname(): string {
  return useSyncExternalStore(
    subscribe,
    () => location.pathname,
    () => location.pathname,
  );
}

export function useSearchParams(): URLSearchParams {
  const search = useSyncExternalStore(
    subscribe,
    () => location.search,
    () => location.search,
  );
  return new URLSearchParams(search);
}
```

**`matchMedia.ts` implementation (exact):**

```ts
import { vi } from 'vitest';

// phase-8 task-14 (DESIGN.md §6): jsdom has no `matchMedia`, so MUI's `useMediaQuery` falls
// back to `false` — every responsive branch reads as desktop. Install a stub that answers
// `matches` for every query; the returned function restores jsdom's original state.
export function stubMatchMedia(matches: boolean): () => void {
  const target = window as Window & { matchMedia?: typeof window.matchMedia };
  const original = target.matchMedia;
  target.matchMedia = vi.fn((query: string) => ({
    matches,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(() => false),
  })) as unknown as typeof window.matchMedia;
  return () => {
    if (original === undefined) {
      delete target.matchMedia;
    } else {
      target.matchMedia = original;
    }
  };
}
```

**`useBreakpointDown.ts` (exact):**

```ts
import type { Breakpoint, Theme } from '@mui/material/styles';
import useMediaQuery from '@mui/material/useMediaQuery';

// phase-8 task-14 (DESIGN.md §C1/§C5): the one place `useMediaQuery` is imported
// (FRONTEND-CONVENTIONS §4 — MUI stays behind common/). `'md'` → true below 900px.
export function useBreakpointDown(key: Extract<Breakpoint, 'sm' | 'md' | 'lg'>): boolean {
  return useMediaQuery((theme: Theme) => theme.breakpoints.down(key));
}
```

**`format.ts` (exact):**

```ts
import { PLACEHOLDER_DASH } from './copy';

// phase-8 task-14 (DESIGN.md §C4): one date formatter per app. Local time zone on purpose —
// admin screens only ever render in the browser (RequireSession gates them behind a query that
// is pending during SSR), so there is no server/client mismatch to pin UTC for.
const DATE = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium' });
const DATE_TIME = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' });

export function formatDate(iso: string): string {
  return DATE.format(new Date(iso));
}

export function formatDateTime(iso: string): string {
  return DATE_TIME.format(new Date(iso));
}

export function formatOptionalDateTime(iso: string | null): string {
  return iso === null ? PLACEHOLDER_DASH : formatDateTime(iso);
}
```

## Steps (TDD)

- [ ] **RED — test-author.** Write these files/cases verbatim:

**`src/testing/nextNavigation.test.tsx`**

```tsx
// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { navigation } from '@/testing/nextNavigation';

vi.mock('next/navigation', () => import('@/testing/nextNavigation'));

function useLocationUnderTest() {
  return { pathname: usePathname(), params: useSearchParams(), router: useRouter() };
}

describe('testing/nextNavigation seam', () => {
  beforeEach(() => {
    navigation.reset('/content?status=draft');
  });

  it('reads pathname and search params from the mocked location', () => {
    const { result } = renderHook(() => useLocationUnderTest());

    expect(result.current.pathname).toBe('/content');
    expect(result.current.params.get('status')).toBe('draft');
  });

  it('router.replace() updates the location AND re-renders subscribers', () => {
    const { result } = renderHook(() => useLocationUnderTest());

    act(() => {
      result.current.router.replace('/content?status=published&page=2', { scroll: false });
    });

    expect(result.current.params.get('status')).toBe('published');
    expect(result.current.params.get('page')).toBe('2');
    expect(navigation.replace).toHaveBeenCalledWith('/content?status=published&page=2', {
      scroll: false,
    });
    expect(navigation.search).toBe('?status=published&page=2');
  });

  it('router.push() changes the pathname', () => {
    const { result } = renderHook(() => useLocationUnderTest());

    act(() => {
      result.current.router.push('/connected-apps');
    });

    expect(result.current.pathname).toBe('/connected-apps');
    expect(navigation.push).toHaveBeenCalledWith('/connected-apps');
  });

  it('reset() clears the spies and the location', () => {
    const { result } = renderHook(() => useLocationUnderTest());
    act(() => {
      result.current.router.push('/x');
    });

    navigation.reset();

    expect(navigation.push).not.toHaveBeenCalled();
    expect(navigation.pathname).toBe('/');
    expect(navigation.search).toBe('');
  });
});
```

**`src/components/common/useBreakpointDown/useBreakpointDown.test.tsx`**

```tsx
// @vitest-environment jsdom
import { renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { stubMatchMedia } from '@/testing/matchMedia';

import { useBreakpointDown } from '.';

describe('useBreakpointDown', () => {
  let restore: (() => void) | null = null;

  afterEach(() => {
    restore?.();
    restore = null;
  });

  it('is false in jsdom by default (no matchMedia → MUI falls back to false)', () => {
    const { result } = renderHook(() => useBreakpointDown('md'));

    expect(result.current).toBe(false);
  });

  it('is true when matchMedia reports a match', () => {
    restore = stubMatchMedia(true);

    const { result } = renderHook(() => useBreakpointDown('md'));

    expect(result.current).toBe(true);
  });

  it("asks matchMedia for the theme's md down-query", () => {
    restore = stubMatchMedia(false);

    renderHook(() => useBreakpointDown('md'));

    expect(window.matchMedia).toHaveBeenCalledWith('(max-width:899.95px)');
  });
});
```

**`src/lib/format.test.ts`** (node env — fixtures at 12:00Z so the calendar date is the same in
every time zone from UTC−11 to UTC+11; the time-of-day is regex-matched)

```ts
import { describe, expect, it } from 'vitest';

import { formatDate, formatDateTime, formatOptionalDateTime } from './format';

describe('lib/format', () => {
  it('formatDate renders a medium en-US date', () => {
    expect(formatDate('2026-03-15T12:00:00Z')).toBe('Mar 15, 2026');
  });

  it('formatDateTime appends a short time', () => {
    // `\s` (not a literal space) — ICU ≥ 72 emits U+202F before AM/PM.
    expect(formatDateTime('2026-03-15T12:00:00Z')).toMatch(/^Mar 15, 2026, \d{1,2}:\d{2}\s[AP]M$/);
  });

  it('formatOptionalDateTime renders the dash placeholder for null', () => {
    expect(formatOptionalDateTime(null)).toBe('—');
    expect(formatOptionalDateTime('2026-03-15T12:00:00Z')).toMatch(/^Mar 15, 2026, /);
  });
});
```

**`src/components/common/EmptyState/Component.test.tsx`**

```tsx
// @vitest-environment jsdom
import { render, screen, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { EmptyState } from '.';

describe('EmptyState', () => {
  it('renders title, description and the action inside the status region', () => {
    render(
      <EmptyState
        title="No content yet"
        description="Create your first article to get started."
        action={<button type="button">Create your first article</button>}
      />,
    );

    const status = screen.getByRole('status');
    expect(within(status).getByText('No content yet')).toBeInTheDocument();
    expect(within(status).getByText('Create your first article to get started.')).toBeInTheDocument();
    expect(
      within(status).getByRole('button', { name: 'Create your first article' }),
    ).toBeInTheDocument();
  });

  it('renders the requested icon (hidden from assistive tech) instead of the default', () => {
    const { container } = render(<EmptyState message="Nothing here" icon="SmartToy" />);

    const svg = container.querySelector('svg[data-testid="SmartToyIcon"]');
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute('aria-hidden', 'true');
  });

  it('keeps the single-message form unchanged', () => {
    render(<EmptyState message="No content found." />);

    expect(screen.getByRole('status')).toHaveTextContent('No content found.');
  });
});
```

**`src/components/common/IconButton/Component.test.tsx`**

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { IconButton } from '.';

describe('IconButton', () => {
  it('with href renders a link carrying the accessible name', () => {
    render(<IconButton name="Edit" label="Edit Roth IRA Conversion Basics" href="/content/1" />);

    const link = screen.getByRole('link', { name: 'Edit Roth IRA Conversion Basics' });
    expect(link).toHaveAttribute('href', '/content/1');
  });

  it('with onClick renders a button that fires the handler', async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<IconButton name="Delete" label="Delete Foo" onClick={onClick} />);

    await user.click(screen.getByRole('button', { name: 'Delete Foo' }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('color="inherit" and edge="start" reach MUI (AppBar menu-button idiom)', () => {
    render(<IconButton name="Menu" label="Open navigation" onClick={() => {}} color="inherit" edge="start" />);

    const button = screen.getByRole('button', { name: 'Open navigation' });
    expect(button).toHaveClass('MuiIconButton-colorInherit');
    expect(button).toHaveClass('MuiIconButton-edgeStart');
  });

  it('tooltip shows on hover while the label stays the accessible name', async () => {
    const user = userEvent.setup();
    render(<IconButton name="Delete" label="Delete Foo" onClick={() => {}} tooltip="Delete" />);

    const button = screen.getByRole('button', { name: 'Delete Foo' });
    await user.hover(button);

    expect(await screen.findByRole('tooltip')).toHaveTextContent('Delete');
    expect(button).toHaveAccessibleName('Delete Foo');
  });
});
```

**Append to `src/components/common/TextField/Component.test.tsx`** (inside the existing
`describe`):

```tsx
  it('monospace renders the input in a monospace font family', () => {
    render(<TextField label="Body" value="" onChange={() => {}} multiline monospace />);

    expect(screen.getByRole('textbox', { name: 'Body' })).toHaveStyle({ fontFamily: 'monospace' });
  });
```

**`src/components/common/Autocomplete/Component.test.tsx`** (new)

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Autocomplete } from '.';

describe('Autocomplete', () => {
  it('offers the provided options in the popup and commits a picked one', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <Autocomplete
        label="Tags"
        value={[]}
        onChange={onChange}
        options={['retirement', 'tax-planning']}
      />,
    );

    await user.click(screen.getByRole('combobox', { name: 'Tags' }));
    await user.click(await screen.findByRole('option', { name: 'retirement' }));

    expect(onChange).toHaveBeenLastCalledWith(['retirement']);
  });

  it('still accepts free text with Enter when options are given', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Autocomplete label="Tags" value={[]} onChange={onChange} options={['retirement']} />);

    await user.type(screen.getByRole('combobox', { name: 'Tags' }), 'estate{Enter}');

    expect(onChange).toHaveBeenLastCalledWith(['estate']);
  });
});
```

**Append to `src/components/common/Icon/Component.test.tsx`**:

```tsx
  it('registers the sub-phase C glyphs', () => {
    for (const name of ['SmartToy', 'Link', 'ExpandMore', 'Send', 'Stop'] as const) {
      const { unmount } = render(<Icon name={name} label={name} />);
      expect(screen.getByRole('img', { name })).toBeInTheDocument();
      unmount();
    }
  });
```

**Append to `src/lib/copy.test.ts`** (new `it` in the existing describe; add `APP_NAME` to the
import):

```ts
  it('owns the app name used by the shell wordmark and the sign-in card', () => {
    expect(APP_NAME).toBe('AdvisorDesk Admin');
  });
```

- [ ] **Run RED:** `pnpm -C apps/admin test` → the new files fail to resolve
  (`@/testing/*`, `useBreakpointDown`, `lib/format`); EmptyState/IconButton/TextField/
  Autocomplete/Icon/copy cases fail on missing props/registry entries; `pnpm -C apps/admin
  type-check` reports the new prop/registry names as errors.

- [ ] **GREEN — implementer:** create the seams and hook exactly as in Interfaces; copy the
  three pass-throughs from apps/client; extend the four primitives; register the icons; add
  `APP_NAME`; update the barrel. `IconButton` gains `'use client'` and the same
  `isInternalHref` helper as `common/Button` (internal `href` → `component={Link}`); `onClick`
  is now optional and the `label` still lands on the element as `aria-label`. `EmptyState`
  keeps the current `Icon name="Article" size="large"` default.

- [ ] **Run GREEN:** `pnpm -C apps/admin test` (full suite, all green); `pnpm -C apps/admin
  type-check`.

- [ ] **Gates:** `pnpm gates:admin` → clean. Also `pnpm -C apps/admin build` → exit 0 (proves
  `src/testing/*` importing `vitest` does not break the Next type-check pass). No screenshots
  (no screen changes).

- [ ] **Commit:**
  `git add apps/admin/src/testing apps/admin/src/components/common apps/admin/src/lib/format.ts apps/admin/src/lib/format.test.ts apps/admin/src/lib/copy.ts apps/admin/src/lib/copy.test.ts`
  `git commit -m "feat(admin): sub-phase C foundation — navigation/matchMedia test seams, useBreakpointDown, lib/format, primitive extensions (p8 t14)"`

## Verify

```bash
pnpm -C apps/admin test -- testing useBreakpointDown format EmptyState IconButton TextField Autocomplete Icon copy
pnpm gates:admin && pnpm -C apps/admin build
```

## Acceptance

- The navigation seam re-renders subscribers on `replace`/`push` (proven by its own test);
  `stubMatchMedia(true)` flips `useBreakpointDown('md')` to `true`.
- `formatDate`/`formatDateTime`/`formatOptionalDateTime` exported and tested; no other module
  formats dates by hand after tasks 17–21 migrate to them.
- `EmptyState` `icon`/`action`, `IconButton` `href`, `TextField` `monospace`, `Autocomplete`
  `options`, five new icons, `Grid`/`Chip`/`CircularProgress`, `useBreakpointDown`, `APP_NAME`
  all exported; every existing test still green; build green.
