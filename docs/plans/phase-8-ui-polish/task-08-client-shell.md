---
id: p8-t08
phase: phase-8-ui-polish
depends_on: [p8-t07]
status: pending
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: sonnet
---

# Task 08 — Client shell: `SiteHeader`, `SiteNav`, `SiteFooter` (apps/client, B1)

## Goal

Give the public site a real shell: a white header with the wordmark and two nav links (active
one highlighted), and a footer carrying the PRD §8 disclaimer — mounted once in
`app/layout.tsx` so every page (including 404 and loading states) gets it. The home page loses
its bare "Ask a question" text link, and the disclaimer moves out of `ArticleScreen` into
`lib/copy.ts` (B3 re-adds it to the article as an `Alert`).

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §2 (principles) and §4 B1.
- `docs/FRONTEND-CONVENTIONS.md` §3, §4, §6 (RSC vs client islands), §7, §9.
- `apps/client/src/app/layout.tsx` (keep the `next/font` lines and the `<html lang="en"
  className=...>` line byte-identical — `layout.fonts.test.ts` pins them).
- `apps/client/src/app/page.tsx` (the inline `<nav>` to remove).
- `apps/client/src/components/common/{AppBar,Toolbar,Box,Link,Typography,PageContainer}/` and
  `common/index.ts` (barrel).
- `apps/client/src/components/common/Link/Component.tsx` — the `'use client'` leaf precedent and
  its comment on why (functions across the RSC boundary).
- `apps/client/src/components/common/Button/Component.test.tsx` — the `vi.mock('next/link')`
  marker idiom (framework module mocks are acceptable; our own components/hooks are not).
- `apps/client/src/components/content/ContentListScreen/Component.test.tsx` — the "empty list has
  no link" pin (unchanged by this task: the nav link leaves `page.tsx`, so the screen is still
  link-free when empty).
- `apps/client/src/components/content/ArticleScreen/Component.tsx` — where `DISCLAIMER` lives today.
- `apps/client/src/lib/copy.ts`, `apps/client/src/lib/metadata.ts` (`SITE_NAME`).

## Files

**Create**
- `src/components/shell/SiteHeader/{Component.tsx, index.ts, Component.test.tsx}` (zero-prop)
- `src/components/shell/SiteNav/{Component.tsx, index.ts, Component.test.tsx}` (zero-prop, `'use client'`)
- `src/components/shell/SiteFooter/{Component.tsx, index.ts, Component.test.tsx}` (zero-prop)

**Modify**
- `src/app/layout.tsx` — mount header/footer around `{children}` inside a full-height flex column.
- `src/app/page.tsx` — remove the inline `<nav>` and its `Link`/`Typography` imports.
- `src/lib/copy.ts` — add the constants below; `DISCLAIMER` moves here from `ArticleScreen`.
- `src/components/content/ArticleScreen/Component.tsx` — import `DISCLAIMER` from `@/lib/copy`
  (delete the local const; nothing else changes — B3 restyles the article).
- `src/components/common/PageContainer/Component.tsx` — add `flexGrow: 1` to the `sx` so the
  footer sits at the bottom of short pages.

## Interfaces

**Consumes:** `AppBar`, `Toolbar`, `Box`, `Link`, `Typography` from `@/components/common`;
`SITE_NAME` from `@/lib/metadata`; `usePathname` from `next/navigation`.

**Produces exactly:**

```ts
// src/lib/copy.ts — appended
export const NAV_ARTICLES_LABEL = 'Articles';
export const NAV_ASK_LABEL = 'Ask a question';
/** PRD §8 verbatim — the seed-content disclaimer, shown in the footer and on every article. */
export const DISCLAIMER = 'Sample content for demonstration purposes — not financial advice.';
```

**`SiteNav/Component.tsx` — exact (the only client island in the shell):**

```tsx
'use client';

import { usePathname } from 'next/navigation';

import { Box, Link } from '@/components/common';
import { NAV_ARTICLES_LABEL, NAV_ASK_LABEL } from '@/lib/copy';

// phase-8 task-08 (DESIGN.md §B1). The one piece of the shell that needs the browser: the
// active link comes from `usePathname`. Kept as its own leaf so `SiteHeader` stays a Server
// Component (docs/FRONTEND-CONVENTIONS.md §6 — push 'use client' down to the smallest leaf).
const NAV_ITEMS = [
  { label: NAV_ARTICLES_LABEL, href: '/' },
  { label: NAV_ASK_LABEL, href: '/chat' },
] as const;

function isActive(pathname: string, href: string): boolean {
  return href === '/' ? pathname === '/' || pathname.startsWith('/content') : pathname.startsWith(href);
}

export default function Component() {
  const pathname = usePathname();

  return (
    <Box component="nav" aria-label="Primary" sx={{ display: 'flex', gap: 3 }}>
      {NAV_ITEMS.map((item) => {
        const active = isActive(pathname, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? 'page' : undefined}
            underline="none"
            sx={{ fontWeight: active ? 600 : 500, color: active ? 'primary.main' : 'text.secondary' }}
          >
            {item.label}
          </Link>
        );
      })}
    </Box>
  );
}
```

**`SiteHeader/Component.tsx` — exact:**

```tsx
import { AppBar, Box, Link, Toolbar, Typography } from '@/components/common';
import { SITE_NAME } from '@/lib/metadata';

import { SiteNav } from '../SiteNav';

// phase-8 task-08 (DESIGN.md §B1): a conventional content-site header — white, bottom border,
// no shadow; wordmark left, two links right. Server Component; `SiteNav` is the client leaf.
export default function Component() {
  return (
    <AppBar
      position="static"
      color="inherit"
      elevation={0}
      sx={{ bgcolor: 'background.paper', borderBottom: 1, borderColor: 'divider' }}
    >
      <Toolbar sx={{ maxWidth: 'lg', width: '100%', mx: 'auto', justifyContent: 'space-between' }}>
        <Typography variant="h5" component="span" sx={{ fontFamily: 'var(--font-heading), Georgia, serif' }}>
          <Link href="/" underline="none" color="inherit" aria-label={`${SITE_NAME} home`}>
            {SITE_NAME}
          </Link>
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <SiteNav />
        </Box>
      </Toolbar>
    </AppBar>
  );
}
```

(`Toolbar` `maxWidth: 'lg'` resolves through the theme's breakpoint value — 1200px — matching
`PageContainer`'s `Container maxWidth="lg"` so the header content aligns with the page content.)

**`SiteFooter/Component.tsx` — exact:**

```tsx
import { Box, Typography } from '@/components/common';
import { DISCLAIMER } from '@/lib/copy';
import { SITE_NAME } from '@/lib/metadata';

// phase-8 task-08 (DESIGN.md §B1, PRD §8): the disclaimer lives in the footer on every page.
export default function Component() {
  return (
    <Box
      component="footer"
      sx={{ borderTop: 1, borderColor: 'divider', mt: 6, py: 3, bgcolor: 'background.paper' }}
    >
      <Box sx={{ maxWidth: 'lg', mx: 'auto', px: 3 }}>
        <Typography variant="body2" color="text.secondary" component="p">
          {DISCLAIMER}
        </Typography>
        <Typography variant="caption" color="text.secondary" component="p" sx={{ mt: 0.5 }}>
          {SITE_NAME}
        </Typography>
      </Box>
    </Box>
  );
}
```

**`app/layout.tsx` body — exact (imports/fonts/`<html>` line unchanged):**

```tsx
      <body>
        <Providers>
          <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
            <SiteHeader />
            {children}
            <SiteFooter />
          </Box>
        </Providers>
      </body>
```

(`Box`, `SiteHeader`, `SiteFooter` imported from `@/components/common`,
`@/components/shell/SiteHeader`, `@/components/shell/SiteFooter`.)

**`app/page.tsx`** — becomes `<PageContainer><ContentListScreen items={items} /></PageContainer>`
(B2 rewrites it again); drop the now-stale comment about the nav link.

## Steps (TDD)

- [ ] **RED — test-author.**

  `SiteNav/Component.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SiteNav } from '.';

// phase-8 task-08: the active link follows the route. `next/navigation` is a framework module
// (not one of our components/hooks), so mocking it is within FRONTEND-CONVENTIONS §7.
const pathnameMock = vi.fn<() => string>();
vi.mock('next/navigation', () => ({ usePathname: () => pathnameMock() }));

describe('SiteNav', () => {
  beforeEach(() => {
    pathnameMock.mockReturnValue('/');
  });

  it('renders Articles → / and Ask a question → /chat inside a Primary navigation landmark', () => {
    render(<SiteNav />);

    const nav = screen.getByRole('navigation', { name: 'Primary' });
    expect(nav).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Articles' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: 'Ask a question' })).toHaveAttribute('href', '/chat');
  });

  it('marks Articles current on / and on article pages, and Ask a question current on /chat', () => {
    pathnameMock.mockReturnValue('/content/medicare-basics');
    const { unmount } = render(<SiteNav />);
    expect(screen.getByRole('link', { name: 'Articles' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Ask a question' })).not.toHaveAttribute('aria-current');
    unmount();

    pathnameMock.mockReturnValue('/chat');
    render(<SiteNav />);
    expect(screen.getByRole('link', { name: 'Ask a question' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Articles' })).not.toHaveAttribute('aria-current');
  });
});
```

  `SiteHeader/Component.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi } from 'vitest';

import { SiteHeader } from '.';

vi.mock('next/navigation', () => ({ usePathname: () => '/' }));

describe('SiteHeader', () => {
  it('renders a banner with the wordmark linking home and the primary navigation', () => {
    render(<SiteHeader />);

    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'AdvisorDesk home' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('navigation', { name: 'Primary' })).toBeInTheDocument();
  });
});
```

  `SiteFooter/Component.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { SiteFooter } from '.';

describe('SiteFooter', () => {
  it('renders a contentinfo landmark carrying the PRD §8 disclaimer', () => {
    render(<SiteFooter />);

    expect(screen.getByRole('contentinfo')).toHaveTextContent(
      'Sample content for demonstration purposes — not financial advice.',
    );
  });
});
```

  `src/lib/copy.test.ts` (client — create; node env):

```ts
import { describe, expect, it } from 'vitest';

import { DISCLAIMER, NAV_ARTICLES_LABEL, NAV_ASK_LABEL } from './copy';

describe('client copy module', () => {
  it('owns the nav labels and the PRD §8 disclaimer verbatim', () => {
    expect(NAV_ARTICLES_LABEL).toBe('Articles');
    expect(NAV_ASK_LABEL).toBe('Ask a question');
    expect(DISCLAIMER).toBe('Sample content for demonstration purposes — not financial advice.');
  });
});
```

  Existing `ArticleScreen/Component.test.tsx` keeps asserting the disclaimer text on the
  article (still true — the constant merely moved).

- [ ] **Run RED:** `pnpm -C apps/client test -- shell copy` → FAIL (modules missing; `copy`
  lacks the three exports).

- [ ] **GREEN — implementer:** copy constants → `SiteNav` → `SiteHeader` → `SiteFooter` →
  `PageContainer` flexGrow → `layout.tsx` → `page.tsx` → `ArticleScreen` import swap.

- [ ] **Run GREEN:** same command → PASS; `pnpm -C apps/client type-check`; full
  `pnpm -C apps/client test` (the `layout.fonts` pin and the ContentListScreen "no link when
  empty" pin must still pass).

- [ ] **Screenshots** (dev server with `API_URL=https://api.advisordesk.tyagiakanksha.com`; use
  an http-served page with 1440×900 and 390×844 iframes — the sandbox cannot resize windows):
  `/`, `/chat`, `/does-not-exist` at both widths — header with wordmark + active link, footer
  with disclaimer, no horizontal scroll at 390.

- [ ] **Gates:** `pnpm gates:client` → clean.

- [ ] **Commit:**
  `git add apps/client/src/components/shell apps/client/src/app/layout.tsx apps/client/src/app/page.tsx apps/client/src/lib/copy.ts apps/client/src/lib/copy.test.ts apps/client/src/components/content/ArticleScreen/Component.tsx apps/client/src/components/common/PageContainer`
  `git commit -m "feat(client): site header, nav, footer shell (p8 t08)"`

## Verify

```bash
pnpm -C apps/client test -- shell copy ArticleScreen ContentListScreen layout.fonts
pnpm gates:client
```

## Acceptance

- Header (`banner`), nav (`navigation` "Primary", `aria-current` on the active link), footer
  (`contentinfo` with the disclaimer) render on every route via the root layout.
- `page.tsx` has no nav; `ArticleScreen` no longer defines `DISCLAIMER`.
- Only `SiteNav` is `'use client'`; no `@mui` import outside `common/`.
- Screenshots at 1440 and 390 attached.
