---
id: p8-t07
phase: phase-8-ui-polish
depends_on: [p8-t04, p8-t06]
status: pending
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: sonnet
---

# Task 07 — Route files + metadata (both apps)

## Goal

Replace Next's black default 404 and the create-next-app favicon with branded ones, add route
`loading.tsx` skeletons, give every page a real `<title>` through one metadata template per app,
and let the client `error.tsx` retry. Also creates the admin's `lib/copy.ts` (the client already
has one) so the new copy lives in the typed module FRONTEND-CONVENTIONS §9 requires.

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §A4 and §2.
- `docs/FRONTEND-CONVENTIONS.md` §3 (pages thin, no screen code under `app/`), §9.
- `apps/client/src/app/{layout.tsx, error.tsx, page.tsx, chat/page.tsx, content/[slug]/page.tsx}`.
- `apps/admin/src/app/{layout.tsx, signin/page.tsx, (app)/layout.tsx, (app)/page.tsx, (app)/content/page.tsx, (app)/content/new/page.tsx, (app)/content/[id]/page.tsx, (app)/connected-apps/page.tsx}`.
- `apps/client/src/lib/copy.ts` (existing typed copy module — the pattern the admin copy follows).
- `apps/client/src/components/common/{Skeleton,Box,Button,PageContainer,Typography,ErrorState,Paper}/` (task 06),
  `apps/admin/src/components/common/{Skeleton,Box,Button,PageContainer,Typography,Paper,Stack}/` (task 04).
- Next.js App Router file conventions: `not-found.tsx` at `app/` root handles every unmatched
  URL for the whole app (so the admin's renders inside `Providers` only — not inside the
  `(app)` group's `AppShell`); `loading.tsx` wraps its segment in a Suspense boundary;
  `icon.tsx` with `next/og`'s `ImageResponse` generates the favicon at build time.

## Files

**Create — client**
- `src/lib/metadata.ts` (+ `metadata.test.ts`)
- `src/app/not-found.tsx` (+ `not-found.test.tsx`)
- `src/app/loading.tsx`, `src/app/content/[slug]/loading.tsx`
- `src/app/icon.tsx`
- `src/components/content/ContentListSkeleton/{Component.tsx, index.ts, Component.test.tsx}` (zero-prop)
- `src/components/content/ArticleSkeleton/{Component.tsx, index.ts, Component.test.tsx}` (zero-prop)
- `src/app/error.test.tsx`

**Create — admin**
- `src/lib/copy.ts` (+ `copy.test.ts`)
- `src/lib/metadata.ts` (+ `metadata.test.ts`)
- `src/app/not-found.tsx` (+ `not-found.test.tsx`)
- `src/app/(app)/loading.tsx`
- `src/app/icon.tsx`
- `src/components/shell/PageSkeleton/{Component.tsx, index.ts, Component.test.tsx}` (zero-prop)

**Modify**
- `apps/client/src/app/layout.tsx` — `export const metadata = rootMetadata` (from `@/lib/metadata`).
- `apps/client/src/app/chat/page.tsx` — `metadata = { title: 'Ask a question' }`.
- `apps/client/src/app/content/[slug]/page.tsx` — `generateMetadata` returns `{ title: article.title }`
  / `{ title: 'Not found' }` (unchanged text; the template now appends the site name).
- `apps/client/src/app/error.tsx` — accepts `reset`, passes an `action`.
- `apps/client/src/lib/copy.ts` — add the new constants below.
- `apps/admin/src/app/layout.tsx` — `metadata = rootMetadata`.
- Admin pages — add `export const metadata: Metadata = { title: '…' }`: `(app)/page.tsx`
  "Dashboard", `(app)/content/page.tsx` "Content", `(app)/content/new/page.tsx` "New content",
  `(app)/content/[id]/page.tsx` "Edit content", `(app)/connected-apps/page.tsx` "Connected apps",
  `signin/page.tsx` "Sign in".
- `apps/admin/src/components/common/ErrorState/Component.tsx` — default message imported from
  `@/lib/copy` (`GENERIC_ERROR_MESSAGE`) instead of the local literal.

**Delete**
- `apps/client/src/app/favicon.ico`, `apps/admin/src/app/favicon.ico` (both are the untouched
  create-next-app default — `md5sum` shows them identical).

## Interfaces

**Produces exactly:**

```ts
// apps/client/src/lib/copy.ts — appended
export const NOT_FOUND_TITLE = 'Page not found';
export const NOT_FOUND_MESSAGE = 'The page you’re looking for doesn’t exist or has been removed.';
export const BACK_TO_ARTICLES_LABEL = 'Back to articles';
export const PAGE_ERROR_MESSAGE = 'Something went wrong loading this page. Please try again.';
export const RETRY_LABEL = 'Try again';

// apps/admin/src/lib/copy.ts — new
// Shared, friendly UI copy (docs/FRONTEND-CONVENTIONS.md §9: placeholder and user-facing strings
// come from one typed module per app). Mirrors apps/client/src/lib/copy.ts. phase-8 task-07.
export const GENERIC_ERROR_MESSAGE = 'Something went wrong. Please try again.';
export const NOT_FOUND_TITLE = 'Page not found';
export const NOT_FOUND_MESSAGE = 'The page you’re looking for doesn’t exist or has been removed.';
export const BACK_TO_DASHBOARD_LABEL = 'Back to dashboard';
export const PLACEHOLDER_DASH = '—';

// apps/client/src/lib/metadata.ts
import type { Metadata } from 'next';
export const SITE_NAME = 'AdvisorDesk';
export const rootMetadata: Metadata = {
  title: { default: SITE_NAME, template: `%s · ${SITE_NAME}` },
  description: 'Ask questions about our published research and insights.',
};
// apps/admin/src/lib/metadata.ts — SITE_NAME = 'AdvisorDesk Admin', description 'AdvisorDesk internal admin console.'
```

**`apps/client/src/app/not-found.tsx` — exact:**

```tsx
import { Button, PageContainer, Typography } from '@/components/common';
import { BACK_TO_ARTICLES_LABEL, NOT_FOUND_MESSAGE, NOT_FOUND_TITLE } from '@/lib/copy';

// phase-8 task-07 (DESIGN.md §A4): Next's default 404 is a black full-screen page — off-brand for
// a navy/gold content site. Root-level, so it handles every unmatched URL and `notFound()` calls.
export default function NotFound() {
  return (
    <PageContainer maxWidth="sm">
      <Typography variant="h1" component="h1" gutterBottom>
        {NOT_FOUND_TITLE}
      </Typography>
      <Typography component="p" sx={{ mb: 3 }}>
        {NOT_FOUND_MESSAGE}
      </Typography>
      <Button href="/" variant="outlined">
        {BACK_TO_ARTICLES_LABEL}
      </Button>
    </PageContainer>
  );
}
```

**`apps/admin/src/app/not-found.tsx` — exact** (renders without the AppShell — see Context — so it
gets its own centred card):

```tsx
import { Button, PageContainer, Paper, Typography } from '@/components/common';
import { BACK_TO_DASHBOARD_LABEL, NOT_FOUND_MESSAGE, NOT_FOUND_TITLE } from '@/lib/copy';

// phase-8 task-07 (DESIGN.md §A4). Root-level not-found handles every unmatched URL and renders
// under the root layout only (no AppShell — route groups don't wrap unmatched URLs), hence the
// self-contained card.
export default function NotFound() {
  return (
    <PageContainer>
      <Paper variant="outlined" sx={{ p: 4, maxWidth: 480, mx: 'auto', mt: 8 }}>
        <Typography variant="h1" component="h1" gutterBottom>
          {NOT_FOUND_TITLE}
        </Typography>
        <Typography component="p" sx={{ mb: 3 }}>
          {NOT_FOUND_MESSAGE}
        </Typography>
        <Button href="/" variant="outlined">
          {BACK_TO_DASHBOARD_LABEL}
        </Button>
      </Paper>
    </PageContainer>
  );
}
```

**`apps/client/src/app/error.tsx` — exact:**

```tsx
'use client';

import { ErrorState } from '@/components/common';
import { PAGE_ERROR_MESSAGE, RETRY_LABEL } from '@/lib/copy';

// Next.js error-boundary convention: MUST be a Client Component. Friendly copy via `ErrorState`,
// never the raw thrown `Error` (docs/FRONTEND-CONVENTIONS.md §9). phase-8 task-07: `reset` lets
// the reader retry the segment instead of reloading the tab.
export default function Error({ reset }: { reset: () => void }) {
  return <ErrorState message={PAGE_ERROR_MESSAGE} action={{ label: RETRY_LABEL, onClick: reset }} />;
}
```

**`icon.tsx` — exact (both apps):**

```tsx
import { ImageResponse } from 'next/og';

export const size = { width: 32, height: 32 };
export const contentType = 'image/png';

// phase-8 task-07 (DESIGN.md §A4): generated favicon — navy rounded square, white serif "A".
// No binary asset to maintain; the create-next-app favicon.ico was deleted in the same commit.
export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#1E3A5F',
          borderRadius: 7,
          color: '#FFFFFF',
          fontSize: 22,
          fontFamily: 'Georgia, serif',
          fontWeight: 700,
        }}
      >
        A
      </div>
    ),
    size,
  );
}
```

**Skeleton components (zero-prop, `role="status"` `aria-label="Loading"` on the wrapper so the
loading state is explicit — FRONTEND-CONVENTIONS §9):**

```tsx
// client components/content/ContentListSkeleton/Component.tsx
import { Box, Skeleton } from '@/components/common';

const PLACEHOLDER_COUNT = 6;

// phase-8 task-07: what app/loading.tsx shows while the RSC list fetch is in flight — the same
// footprint as the cards it replaces, so nothing jumps when data lands.
export default function Component() {
  return (
    <Box role="status" aria-label="Loading">
      {Array.from({ length: PLACEHOLDER_COUNT }, (_, index) => (
        <Box key={index} sx={{ mb: 2, p: 2, border: 1, borderColor: 'divider', borderRadius: 1 }}>
          <Skeleton variant="text" width="60%" height={28} />
          <Skeleton variant="text" width="30%" />
        </Box>
      ))}
    </Box>
  );
}
```

```tsx
// client components/content/ArticleSkeleton/Component.tsx
import { Box, Skeleton } from '@/components/common';

const LINE_COUNT = 8;

export default function Component() {
  return (
    <Box role="status" aria-label="Loading">
      <Skeleton variant="text" width="70%" height={44} />
      <Skeleton variant="text" width="25%" sx={{ mb: 3 }} />
      {Array.from({ length: LINE_COUNT }, (_, index) => (
        <Skeleton key={index} variant="text" width={index % 3 === 2 ? '80%' : '100%'} />
      ))}
    </Box>
  );
}
```

```tsx
// admin components/shell/PageSkeleton/Component.tsx
import { Box, Skeleton, Stack } from '@/components/common';

const ROW_COUNT = 5;

export default function Component() {
  return (
    <Box role="status" aria-label="Loading">
      <Skeleton variant="text" width="30%" height={40} sx={{ mb: 3 }} />
      <Stack spacing={1.5}>
        {Array.from({ length: ROW_COUNT }, (_, index) => (
          <Skeleton key={index} variant="rectangular" height={48} />
        ))}
      </Stack>
    </Box>
  );
}
```

`loading.tsx` files are thin — this is the client root one; the other two swap the skeleton
(`ArticleSkeleton` for `content/[slug]/loading.tsx`, `PageSkeleton` from
`@/components/shell/PageSkeleton` for the admin `(app)/loading.tsx`):

```tsx
import { PageContainer } from '@/components/common';
import { ContentListSkeleton } from '@/components/content/ContentListSkeleton';

// phase-8 task-07: Next renders this inside a Suspense boundary while the segment's RSC data
// loads (docs/FRONTEND-CONVENTIONS.md §9 — never a silent blank region).
export default function Loading() {
  return (
    <PageContainer>
      <ContentListSkeleton />
    </PageContainer>
  );
}
```

Each skeleton folder's `index.ts` is `export { default as <Name> } from './Component';`.

## Steps (TDD)

- [ ] **RED — test-author.**

  `apps/client/src/lib/metadata.test.ts` (node env; admin copy asserts `'AdvisorDesk Admin'`):

```ts
import { describe, expect, it } from 'vitest';

import { rootMetadata, SITE_NAME } from './metadata';

describe('root metadata', () => {
  it('gives every page a "<page> · AdvisorDesk" title through one template', () => {
    expect(SITE_NAME).toBe('AdvisorDesk');
    expect(rootMetadata.title).toEqual({ default: 'AdvisorDesk', template: '%s · AdvisorDesk' });
  });
});
```

  `apps/client/src/app/not-found.test.tsx` (admin copy expects `Back to dashboard`):

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import NotFound from './not-found';

describe('not-found route', () => {
  it('renders a branded heading, a friendly message, and a way back', () => {
    render(<NotFound />);

    expect(screen.getByRole('heading', { level: 1, name: 'Page not found' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to articles' })).toHaveAttribute('href', '/');
  });
});
```

  `apps/client/src/app/error.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import Error from './error';

describe('error route', () => {
  it('shows friendly copy and retries the segment through reset', async () => {
    const reset = vi.fn();
    render(<Error reset={reset} />);

    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong loading this page.');
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));

    expect(reset).toHaveBeenCalledTimes(1);
  });
});
```

  Skeleton tests (one per component; `ArticleSkeleton` and `PageSkeleton` identical apart from
  the import):

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { ContentListSkeleton } from '.';

describe('ContentListSkeleton', () => {
  it('announces itself as a loading status region', () => {
    render(<ContentListSkeleton />);

    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument();
  });
});
```

  `apps/admin/src/lib/copy.test.ts` (node env):

```ts
import { describe, expect, it } from 'vitest';

import { GENERIC_ERROR_MESSAGE, NOT_FOUND_TITLE, PLACEHOLDER_DASH } from './copy';

describe('admin copy module', () => {
  it('owns the shared placeholder and error strings', () => {
    expect(PLACEHOLDER_DASH).toBe('—');
    expect(GENERIC_ERROR_MESSAGE).toBe('Something went wrong. Please try again.');
    expect(NOT_FOUND_TITLE).toBe('Page not found');
  });
});
```

- [ ] **Run RED:** `pnpm -C apps/client test -- metadata not-found error Skeleton && pnpm -C apps/admin test -- metadata not-found copy Skeleton`
  Expected: FAIL — modules missing; `error.tsx` has no button.

- [ ] **GREEN — implementer:** copy modules → metadata modules + layout/page `metadata` →
  skeleton components → `loading.tsx` files → `not-found.tsx` files → `error.tsx` → `icon.tsx` +
  `git rm` both `favicon.ico` → admin `ErrorState` default message from `@/lib/copy`.

- [ ] **Run GREEN:** same commands → PASS. Type-check both apps.

- [ ] **Full suites:** `pnpm -C apps/client test && pnpm -C apps/admin test` → green.

- [ ] **Build + icon proof:** `API_URL=http://localhost:8000 pnpm -C apps/client build` and the
  admin equivalent → the route list includes `/icon`. Then `pnpm -C apps/client dev` and
  `curl -sI http://localhost:3000/icon | grep -i content-type` → `image/png`.

- [ ] **Screenshots:** client `/does-not-exist` and admin `/does-not-exist` (signed in or not) at
  1440 and 390; the browser tab with the navy "A" icon; client `/` with network throttled to
  "Slow 3G" showing the skeleton cards.

- [ ] **Gates:** `pnpm gates:client && pnpm gates:admin` → clean.

- [ ] **Commit:**
  `git add apps/client/src/app apps/client/src/lib apps/client/src/components/content/ContentListSkeleton apps/client/src/components/content/ArticleSkeleton apps/admin/src/app apps/admin/src/lib apps/admin/src/components/shell/PageSkeleton apps/admin/src/components/common/ErrorState`
  `git commit -m "feat(web): branded not-found, loading skeletons, generated favicon, title templates, error retry (p8 t07)"`

## Verify

```bash
pnpm -C apps/client test -- metadata not-found error Skeleton
pnpm -C apps/admin test -- metadata not-found copy Skeleton
pnpm gates:client && pnpm gates:admin
```

## Acceptance

- Both 404s are branded and offer a way back; both apps serve `/icon` as `image/png`; no
  `favicon.ico` remains under `src/app/`.
- Every page title follows `<page> · <site>`; the article page keeps `article.title` as the page part.
- `loading.tsx` files are ≤ 10 lines each; skeleton components live under `components/`.
- Client `error.tsx` retries via `reset`; admin `ErrorState` default copy comes from `lib/copy.ts`.
- Reviewer (Sonnet) checks the five dimensions with file:line evidence, and that no screen
  code crept into `app/`.
