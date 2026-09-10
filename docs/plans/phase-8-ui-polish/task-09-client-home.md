---
id: p8-t09
phase: phase-8-ui-polish
depends_on: [p8-t08]
status: pending
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: sonnet
---

# Task 09 — Client home: header block, tag filter, article grid (apps/client, B2)

## Goal

Turn the bare card list into a real landing page: an "Articles" heading with a one-line
description and one gold call-to-action, a row of tag chips that filter the list through the
URL (`/?tag=retirement`, server-side in the RSC), and a responsive 1/2/3-column grid of equal-
height cards showing title, date, and tag links. Distinct empty states for "no content" vs
"no match".

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §2 and §4 B2.
- `docs/FRONTEND-CONVENTIONS.md` §3 (leaf components under `<Screen>/components/`), §6 (RSC
  fetches, client islands), §7, §9.
- `apps/client/src/app/page.tsx` (after task 08: thin, no nav), `apps/client/src/lib/publicApi.ts`
  (`getPublishedContent()` — bare array sorted `published_at` desc).
- `apps/client/src/components/content/ContentListScreen/{Component.tsx, interface.ts, Component.test.tsx}`
  — the existing screen and its pins (rewritten in this task, see RED).
- `apps/client/src/components/common/{Grid,Card,Chip,Button,EmptyState,Link,Stack,Typography,Box}/`
  and `common/index.ts`. `Chip` is a generic pass-through (`<Chip<'a'> component="a" href …>`
  renders a real anchor — see its interface comment). `EmptyState` takes `icon?` and
  `action?: {label, href}`.
- `apps/client/src/components/common/Link/Component.tsx` — `'use client'` leaf; passing it as
  `component={Link}` from a Server Component would cross the RSC boundary with a function, so
  the two leaves that render tag chips as links are client islands.
- `apps/client/src/lib/formatDate.ts` (`formatPublishedDate`), `apps/client/src/lib/copy.ts`.
- `apps/client/src/components/content/ContentListSkeleton/Component.tsx` (task 07) — update to
  the grid shape.
- `apps/client/src/types/api/content.ts` — `PublicContentSummary = { slug, title, tags: string[], published_at }`.

## Files

**Create**
- `src/lib/filterByTag.ts` + `filterByTag.test.ts`
- `src/components/content/ArticleCard/{Component.tsx, interface.ts, index.ts, Component.test.tsx}` (`'use client'`, shared with B3's related list)
- `src/components/content/ContentListScreen/components/TagFilter/{Component.tsx, interface.ts, index.ts, Component.test.tsx}` (`'use client'`)

**Modify**
- `src/components/content/ContentListScreen/{Component.tsx, interface.ts, Component.test.tsx}`
- `src/components/content/ContentListSkeleton/Component.tsx` — 6 card skeletons in the same grid.
- `src/app/page.tsx` — `searchParams`, filtering, new props.
- `src/lib/copy.ts` — constants below.

## Interfaces

**Produces exactly:**

```ts
// src/lib/copy.ts — appended
export const HOME_TITLE = 'Articles';
export const HOME_DESCRIPTION =
  'Plain-English explainers on retirement, insurance, taxes and college savings.';
export const HOME_CTA_LABEL = 'Ask a question';
export const ALL_TAGS_LABEL = 'All';
export const NO_CONTENT_MESSAGE = 'No published content yet.';
export const SHOW_ALL_LABEL = 'Show all';
export function noArticlesTaggedMessage(tag: string): string {
  return `No articles tagged '${tag}'.`;
}

// src/lib/filterByTag.ts
import type { PublicContentSummary } from '@/types';
/** Unique tags across `items`, sorted A→Z (locale-insensitive, plain `<`). */
export function uniqueTags(items: PublicContentSummary[]): string[];
/** `tag === null` → `items` unchanged; otherwise only items whose `tags` include `tag` (exact match). */
export function filterByTag(items: PublicContentSummary[], tag: string | null): PublicContentSummary[];

// ArticleCard/interface.ts
import type { PublicContentSummary } from '@/types';
export interface ArticleCardProps {
  item: PublicContentSummary;
}

// TagFilter/interface.ts
export interface TagFilterProps {
  tags: string[];              // from uniqueTags(all items)
  selectedTag: string | null;  // null = "All"
}

// ContentListScreen/interface.ts
import type { PublicContentSummary } from '@/types';
export interface ContentListScreenProps {
  /** Items to render — already filtered by the page. */
  items: PublicContentSummary[];
  /** Every tag in the full (unfiltered) list. Empty when there is no content at all. */
  tags: string[];
  selectedTag: string | null;
}
```

**Behaviour (`ContentListScreen/Component.tsx`, dumb):**
- Header block: `Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between"
  alignItems={{ sm: 'center' }} spacing={2} sx={{ mb: 3 }}` → left: `Typography h1`
  `HOME_TITLE` + `Typography body1 color="text.secondary"` `HOME_DESCRIPTION`; right:
  `Button variant="contained" color="secondary" href="/chat"` `HOME_CTA_LABEL` (the page's one
  gold CTA).
- `tags.length > 0` → `<TagFilter tags selectedTag />`.
- `items.length === 0 && selectedTag === null` → `<EmptyState message={NO_CONTENT_MESSAGE} />`.
- `items.length === 0 && selectedTag !== null` → `<EmptyState icon="Search"
  message={noArticlesTaggedMessage(selectedTag)} action={{ label: SHOW_ALL_LABEL, href: '/' }} />`.
- Otherwise `<Grid container spacing={2}>` with `<Grid key={item.slug} size={{ xs: 12, sm: 6, md: 4 }}>
  <ArticleCard item={item} /></Grid>` (MUI 9 Grid API: `size`, not `xs`/`sm` props).

**`ArticleCard/Component.tsx` — exact:**

```tsx
'use client';

import { Box, Card, Chip, Link, Typography } from '@/components/common';
import { formatPublishedDate } from '@/lib/formatDate';

import type { ArticleCardProps } from './interface';

// phase-8 task-09 (DESIGN.md §B2): one article summary card, equal height in a grid. A client
// leaf because the tag chips render through `common/Link` (next/link) as `component` — a
// function prop that cannot cross the RSC boundary from a Server Component parent.
export default function Component({ item }: ArticleCardProps) {
  return (
    <Card sx={{ height: '100%' }}>
      <Typography variant="h4" component="h2" gutterBottom>
        <Link href={`/content/${item.slug}`} underline="hover" color="inherit">
          {item.title}
        </Link>
      </Typography>
      <Typography variant="body2" color="text.secondary" component="p" sx={{ mb: 1.5 }}>
        {formatPublishedDate(item.published_at)}
      </Typography>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
        {item.tags.map((tag) => (
          <Chip<typeof Link>
            key={tag}
            component={Link}
            href={`/?tag=${encodeURIComponent(tag)}`}
            clickable
            label={tag}
            variant="outlined"
          />
        ))}
      </Box>
    </Card>
  );
}
```

**`TagFilter/Component.tsx` — exact:**

```tsx
'use client';

import { Box, Chip, Link } from '@/components/common';
import { ALL_TAGS_LABEL } from '@/lib/copy';

import type { TagFilterProps } from './interface';

// phase-8 task-09 (DESIGN.md §B2): tag chips as links — filtering is a URL, not client state, so
// the page stays an RSC and a filtered list is shareable. Client leaf for the same reason as
// ArticleCard (next/link passed as `component`).
export default function Component({ tags, selectedTag }: TagFilterProps) {
  const options = [{ label: ALL_TAGS_LABEL, tag: null }, ...tags.map((tag) => ({ label: tag, tag }))];

  return (
    <Box component="nav" aria-label="Filter by tag" sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 3 }}>
      {options.map((option) => {
        const selected = option.tag === selectedTag;
        return (
          <Chip<typeof Link>
            key={option.label}
            component={Link}
            href={option.tag === null ? '/' : `/?tag=${encodeURIComponent(option.tag)}`}
            clickable
            label={option.label}
            color={selected ? 'primary' : 'default'}
            variant={selected ? 'filled' : 'outlined'}
            aria-current={selected ? 'page' : undefined}
          />
        );
      })}
    </Box>
  );
}
```

**`app/page.tsx` — exact:**

```tsx
import { PageContainer } from '@/components/common';
import { ContentListScreen } from '@/components/content/ContentListScreen';
import { filterByTag, uniqueTags } from '@/lib/filterByTag';
import { getPublishedContent } from '@/lib/publicApi';

interface PageProps {
  searchParams: Promise<{ tag?: string }>;
}

// PRD §2.2 browse. RSC: fetch + filter server-side from `?tag=` (docs/FRONTEND-CONVENTIONS.md §6)
// so the URL is the filter state — shareable, no client island for the list itself.
export default async function Page({ searchParams }: PageProps) {
  const { tag } = await searchParams;
  const selectedTag = tag && tag.length > 0 ? tag : null;
  const items = await getPublishedContent();

  return (
    <PageContainer>
      <ContentListScreen
        items={filterByTag(items, selectedTag)}
        tags={uniqueTags(items)}
        selectedTag={selectedTag}
      />
    </PageContainer>
  );
}
```

`ContentListSkeleton`: header-line skeleton (`width 30%`, `height 44`) + `Grid container
spacing={2}` of six `Grid size={{ xs: 12, sm: 6, md: 4 }}` items each `Skeleton
variant="rounded" height={140}`; keep `role="status" aria-label={LOADING_LABEL}`.

## Steps (TDD)

- [ ] **RED — test-author.**

  `src/lib/filterByTag.test.ts` (node env):

```ts
import { describe, expect, it } from 'vitest';

import type { PublicContentSummary } from '@/types';

import { filterByTag, uniqueTags } from './filterByTag';

const items: PublicContentSummary[] = [
  { slug: 'a', title: 'A', tags: ['retirement', 'tax-planning'], published_at: '2026-03-01T00:00:00Z' },
  { slug: 'b', title: 'B', tags: ['insurance'], published_at: '2026-02-01T00:00:00Z' },
  { slug: 'c', title: 'C', tags: ['retirement'], published_at: '2026-01-01T00:00:00Z' },
];

describe('uniqueTags', () => {
  it('returns each tag once, sorted A→Z', () => {
    expect(uniqueTags(items)).toEqual(['insurance', 'retirement', 'tax-planning']);
  });

  it('returns an empty array for no items', () => {
    expect(uniqueTags([])).toEqual([]);
  });
});

describe('filterByTag', () => {
  it('returns the items unchanged (same order) for a null tag', () => {
    expect(filterByTag(items, null)).toEqual(items);
  });

  it('keeps only items carrying the tag, preserving order', () => {
    expect(filterByTag(items, 'retirement').map((item) => item.slug)).toEqual(['a', 'c']);
  });

  it('matches tags exactly (no prefix or case folding) and returns [] for an unknown tag', () => {
    expect(filterByTag(items, 'retire')).toEqual([]);
    expect(filterByTag(items, 'Retirement')).toEqual([]);
    expect(filterByTag(items, 'nope')).toEqual([]);
  });
});
```

  `ArticleCard/Component.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { ArticleCard } from '.';

const item = {
  slug: 'roth-ira-conversion-basics',
  title: 'Roth IRA Conversion Basics',
  tags: ['retirement', 'tax-planning'],
  published_at: '2026-01-15T00:00:00Z',
};

describe('ArticleCard', () => {
  it('renders the title as an h2 link to the article, the published date, and tag links to the filter', () => {
    render(<ArticleCard item={item} />);

    const title = screen.getByRole('heading', { level: 2, name: 'Roth IRA Conversion Basics' });
    expect(title).toHaveClass('MuiTypography-h4');
    expect(screen.getByRole('link', { name: 'Roth IRA Conversion Basics' })).toHaveAttribute(
      'href',
      '/content/roth-ira-conversion-basics',
    );
    expect(screen.getByText('Jan 15, 2026')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'retirement' })).toHaveAttribute('href', '/?tag=retirement');
    expect(screen.getByRole('link', { name: 'tax-planning' })).toHaveAttribute('href', '/?tag=tax-planning');
  });
});
```

  `TagFilter/Component.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { TagFilter } from '.';

describe('TagFilter', () => {
  it('renders All first, then one link per tag, inside a "Filter by tag" navigation', () => {
    render(<TagFilter tags={['insurance', 'retirement']} selectedTag={null} />);

    const nav = screen.getByRole('navigation', { name: 'Filter by tag' });
    const links = screen.getAllByRole('link');
    expect(nav).toBeInTheDocument();
    expect(links.map((link) => link.textContent)).toEqual(['All', 'insurance', 'retirement']);
    expect(links[0]).toHaveAttribute('href', '/');
    expect(links[1]).toHaveAttribute('href', '/?tag=insurance');
    expect(links[0]).toHaveAttribute('aria-current', 'page');
  });

  it('marks the selected tag current and All not current', () => {
    render(<TagFilter tags={['insurance', 'retirement']} selectedTag="retirement" />);

    expect(screen.getByRole('link', { name: 'retirement' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'All' })).not.toHaveAttribute('aria-current');
  });

  it('URL-encodes tags with special characters', () => {
    render(<TagFilter tags={['college savings']} selectedTag={null} />);

    expect(screen.getByRole('link', { name: 'college savings' })).toHaveAttribute('href', '/?tag=college%20savings');
  });
});
```

  `ContentListScreen/Component.test.tsx` — REWRITE (the old "no link when empty" pin is
  superseded: the header CTA is a link on every state; the rule becomes "no article links"):

```tsx
// @vitest-environment jsdom
import { render, screen, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import type { PublicContentSummary } from '@/types';

import { ContentListScreen } from '.';

// phase-8 task-09 (DESIGN.md §B2) supersedes the phase-3 pins: the screen now owns the page
// header (h1 + description + the single gold CTA), the tag filter, a responsive grid of
// ArticleCards, and two distinct empty states.
const items: PublicContentSummary[] = [
  { slug: 'roth-ira-conversion-basics', title: 'Roth IRA Conversion Basics', tags: ['retirement', 'tax-planning'], published_at: '2026-01-15T00:00:00Z' },
  { slug: 'estate-planning-101', title: 'Estate Planning 101', tags: ['estate-planning'], published_at: '2025-12-01T00:00:00Z' },
];
const tags = ['estate-planning', 'retirement', 'tax-planning'];

describe('ContentListScreen', () => {
  it('renders the Articles h1, the description, and one CTA link to /chat', () => {
    render(<ContentListScreen items={items} tags={tags} selectedTag={null} />);

    expect(screen.getByRole('heading', { level: 1, name: 'Articles' })).toBeInTheDocument();
    expect(screen.getByText(/Plain-English explainers/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ask a question' })).toHaveAttribute('href', '/chat');
  });

  it('renders the tag filter and one card per item, each linking to /content/{slug}', () => {
    render(<ContentListScreen items={items} tags={tags} selectedTag={null} />);

    expect(screen.getByRole('navigation', { name: 'Filter by tag' })).toBeInTheDocument();
    for (const item of items) {
      expect(screen.getByRole('link', { name: item.title })).toHaveAttribute('href', `/content/${item.slug}`);
    }
  });

  it('shows the no-content empty state with no article links and no tag filter when there is nothing at all', () => {
    render(<ContentListScreen items={[]} tags={[]} selectedTag={null} />);

    const status = screen.getByRole('status');
    expect(status).toHaveTextContent('No published content yet.');
    expect(within(status).queryByRole('link')).toBeNull();
    expect(screen.queryByRole('navigation', { name: 'Filter by tag' })).toBeNull();
  });

  it('shows the no-match empty state with a Show all link when a tag filters everything out', () => {
    render(<ContentListScreen items={[]} tags={tags} selectedTag="insurance" />);

    const status = screen.getByRole('status');
    expect(status).toHaveTextContent("No articles tagged 'insurance'.");
    expect(within(status).getByRole('link', { name: 'Show all' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('navigation', { name: 'Filter by tag' })).toBeInTheDocument();
  });
});
```

- [ ] **Run RED:** `pnpm -C apps/client test -- filterByTag ArticleCard TagFilter ContentListScreen`
  → FAIL (modules missing; screen lacks the new props/regions).

- [ ] **GREEN — implementer:** copy → `filterByTag.ts` → `ArticleCard` → `TagFilter` →
  `ContentListScreen` (+ interface) → `ContentListSkeleton` → `page.tsx`. Type-check; full suite.

- [ ] **Screenshots:** `/` and `/?tag=retirement` at 1440 (3 columns) and 390 (1 column);
  `/?tag=nope` (no-match state). Iframe technique.

- [ ] **Gates:** `pnpm gates:client` → clean.

- [ ] **Commit:**
  `git add apps/client/src/lib/filterByTag.ts apps/client/src/lib/filterByTag.test.ts apps/client/src/lib/copy.ts apps/client/src/components/content/ArticleCard apps/client/src/components/content/ContentListScreen apps/client/src/components/content/ContentListSkeleton apps/client/src/app/page.tsx`
  `git commit -m "feat(client): home header, URL tag filter, responsive article grid (p8 t09)"`

## Verify

```bash
pnpm -C apps/client test -- filterByTag ArticleCard TagFilter ContentListScreen
pnpm gates:client
```

## Acceptance

- `/?tag=x` filters server-side; chips are real links; "All" resets; unknown tag shows the
  no-match state with "Show all".
- Grid is 1/2/3 columns (xs/sm/md); cards equal height; exactly one gold CTA on the page.
- `ArticleCard` and `TagFilter` are the only new client islands; `page.tsx` ≤ 25 lines.
