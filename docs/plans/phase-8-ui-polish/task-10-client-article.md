---
id: p8-t10
phase: phase-8-ui-polish
depends_on: [p8-t09]
status: pending
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: sonnet
---

# Task 10 — Client article page: reading layout, related articles, CTA (apps/client, B3)

## Goal

Make the article page read like an article: a `md`-width column (~70 characters per line
instead of ~135), a back link, a meta line with tag links, the disclaimer as a quiet info
alert, up to three related articles (same-tag first), and a call-to-action into chat. One fetch
per request for the article (React `cache()` dedupes `generateMetadata` + page).

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §2 and §4 B3.
- `docs/FRONTEND-CONVENTIONS.md` §3, §6, §7, §9.
- `apps/client/src/app/content/[slug]/page.tsx`, `apps/client/src/app/content/[slug]/loading.tsx`.
- `apps/client/src/components/content/ArticleScreen/{Component.tsx, interface.ts, Component.test.tsx}`
  (after task 08: `DISCLAIMER` imported from `@/lib/copy`; the test asserts the disclaimer text,
  one h1, `##` → h3).
- `apps/client/src/components/content/ArticleCard/` (task 09 — reused for related articles).
- `apps/client/src/components/content/ArticleSkeleton/Component.tsx` (task 07).
- `apps/client/src/lib/publicApi.ts` (`getContentBySlug`, `getPublishedContent`), `lib/formatDate.ts`,
  `lib/markdown.ts` (`stripLeadingHeading`), `lib/copy.ts`.
- `apps/client/src/components/common/{Alert,Button,Chip,Divider,Grid,Link,Stack,Typography,Box,PageContainer}/`.
- `apps/client/src/types/api/content.ts` — `PublicContentDetail = PublicContentSummary & { body_md }`
  (check the generated schema for the exact field set).

## Files

**Create**
- `src/lib/related.ts` + `related.test.ts`
- `src/components/content/ArticleScreen/components/RelatedArticles/{Component.tsx, interface.ts, index.ts, Component.test.tsx}`

**Modify**
- `src/lib/publicApi.ts` — wrap `getContentBySlug` in `cache()` from `react`.
- `src/components/content/ArticleScreen/{Component.tsx, interface.ts, Component.test.tsx}`.
- `src/app/content/[slug]/page.tsx` — `maxWidth="md"`, fetch the list for related.
- `src/app/content/[slug]/loading.tsx` — `PageContainer maxWidth="md"`.
- `src/lib/copy.ts` — constants below.

## Interfaces

**Produces exactly:**

```ts
// src/lib/copy.ts — appended
export const RELATED_ARTICLES_TITLE = 'Related articles';
export const ASK_ABOUT_TOPIC_LABEL = 'Ask a question about this topic';

// src/lib/related.ts
import type { PublicContentSummary } from '@/types';
/**
 * Up to `max` articles related to `current`: candidates exclude `current.slug`; ordered by the
 * number of shared tags (desc), then `published_at` (desc); if fewer than `max` share a tag, the
 * most recent remaining articles fill the rest. Pure.
 */
export function relatedArticles(
  all: PublicContentSummary[],
  current: Pick<PublicContentSummary, 'slug' | 'tags'>,
  max?: number, // default 3
): PublicContentSummary[];

// src/lib/publicApi.ts
export const getContentBySlug: (slug: string) => Promise<PublicContentDetailDto | null>; // = cache(async (slug) => { …unchanged body… })

// ArticleScreen/interface.ts
import type { PublicContentDetail, PublicContentSummary } from '@/types';
export interface ArticleScreenProps {
  article: PublicContentDetail;
  related: PublicContentSummary[]; // already computed by the page; may be []
}

// RelatedArticles/interface.ts
import type { PublicContentSummary } from '@/types';
export interface RelatedArticlesProps {
  items: PublicContentSummary[]; // renders nothing when empty
}
```

**`ArticleScreen/Component.tsx` — exact:**

```tsx
import { Alert, Box, Button, Chip, Divider, Link, Typography } from '@/components/common';
import { ASK_ABOUT_TOPIC_LABEL, BACK_TO_ARTICLES_LABEL, DISCLAIMER } from '@/lib/copy';
import { formatPublishedDate } from '@/lib/formatDate';
import { stripLeadingHeading } from '@/lib/markdown';

import { Markdown } from '../Markdown';
import { RelatedArticles } from './components/RelatedArticles';
import type { ArticleScreenProps } from './interface';

// PRD §2.2 (detail renders markdown) + §8 (disclaimer). Dumb, synchronous — `article` and
// `related` arrive from the thin async page. phase-8 task-10 (DESIGN.md §B3): reading layout —
// back link, meta line with tag links, one h1 (body `#` stripped, `##` demoted to h3), the
// disclaimer as an outlined info alert, related articles, and a CTA into chat.
export default function Component({ article, related }: ArticleScreenProps) {
  return (
    <article>
      <Link href="/" underline="hover" sx={{ display: 'inline-block', mb: 2 }}>
        ← {BACK_TO_ARTICLES_LABEL}
      </Link>
      <Typography variant="h1" component="h1" gutterBottom>
        {article.title}
      </Typography>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1, mb: 2 }}>
        <Typography variant="body2" color="text.secondary" component="p">
          {formatPublishedDate(article.published_at)}
        </Typography>
        {article.tags.map((tag) => (
          <Chip<'a'>
            key={tag}
            component="a"
            href={`/?tag=${encodeURIComponent(tag)}`}
            clickable
            label={tag}
            variant="outlined"
          />
        ))}
      </Box>
      <Divider sx={{ mb: 3 }} />
      <Markdown markdown={stripLeadingHeading(article.body_md, article.title)} headingOffset={1} />
      <Alert severity="info" variant="outlined" sx={{ mt: 4 }}>
        {DISCLAIMER}
      </Alert>
      <RelatedArticles items={related} />
      <Box sx={{ mt: 4 }}>
        <Button variant="outlined" href="/chat">
          {ASK_ABOUT_TOPIC_LABEL}
        </Button>
      </Box>
    </article>
  );
}
```

(Tag chips here use `component="a"` — plain anchors — because `ArticleScreen` is a Server
Component and `common/Link` is a function it cannot pass across the RSC boundary; a tag click
from an article is a full navigation to the filtered list, which is fine. `ArticleCard` — a
client leaf — keeps next/link.)

**`RelatedArticles/Component.tsx` — exact:**

```tsx
import { Grid, Typography } from '@/components/common';
import { RELATED_ARTICLES_TITLE } from '@/lib/copy';

import { ArticleCard } from '../../../ArticleCard';
import type { RelatedArticlesProps } from './interface';

// phase-8 task-10 (DESIGN.md §B3): up to three related summaries reusing the home page's card.
export default function Component({ items }: RelatedArticlesProps) {
  if (items.length === 0) {
    return null;
  }

  return (
    <Grid container spacing={2} component="section" aria-labelledby="related-articles-heading" sx={{ mt: 4 }}>
      <Grid size={12}>
        <Typography variant="h3" component="h2" id="related-articles-heading">
          {RELATED_ARTICLES_TITLE}
        </Typography>
      </Grid>
      {items.map((item) => (
        <Grid key={item.slug} size={{ xs: 12, sm: 4 }}>
          <ArticleCard item={item} />
        </Grid>
      ))}
    </Grid>
  );
}
```

**`src/lib/related.ts` — exact:**

```ts
import type { PublicContentSummary } from '@/types';

const DEFAULT_MAX = 3;

function sharedTagCount(a: readonly string[], b: readonly string[]): number {
  return a.filter((tag) => b.includes(tag)).length;
}

// phase-8 task-10 (DESIGN.md §B3). Pure: same-tag articles first (most shared tags, then most
// recent), then the most recent others if needed to reach `max`. The public list endpoint has no
// "related" query, and 30 summaries sort in microseconds — a request would cost more than it saves.
export function relatedArticles(
  all: PublicContentSummary[],
  current: Pick<PublicContentSummary, 'slug' | 'tags'>,
  max = DEFAULT_MAX,
): PublicContentSummary[] {
  return all
    .filter((item) => item.slug !== current.slug)
    .map((item) => ({ item, shared: sharedTagCount(item.tags, current.tags) }))
    .sort((a, b) => b.shared - a.shared || b.item.published_at.localeCompare(a.item.published_at))
    .slice(0, max)
    .map(({ item }) => item);
}
```

**`app/content/[slug]/page.tsx`** — `generateMetadata` unchanged; the page fetches
`getContentBySlug(slug)` and `getPublishedContent()` (`Promise.all`), calls `notFound()` on a
missing article, and renders `<PageContainer maxWidth="md"><ArticleScreen article={article}
related={relatedArticles(all, article)} /></PageContainer>`. `getContentBySlug` is wrapped:
`export const getContentBySlug = cache(async (slug: string): Promise<PublicContentDetailDto | null> => { …existing body… });`
with `import { cache } from 'react';` and a comment: React's request-scoped memo dedupes the
`generateMetadata` + page calls for the same slug.

## Steps (TDD)

- [ ] **RED — test-author.**

  `src/lib/related.test.ts` (node env):

```ts
import { describe, expect, it } from 'vitest';

import type { PublicContentSummary } from '@/types';

import { relatedArticles } from './related';

const make = (slug: string, tags: string[], date: string): PublicContentSummary => ({
  slug,
  title: slug,
  tags,
  published_at: date,
});

const all = [
  make('current', ['retirement', 'tax'], '2026-05-01T00:00:00Z'),
  make('two-shared-old', ['retirement', 'tax'], '2025-01-01T00:00:00Z'),
  make('one-shared-new', ['retirement'], '2026-04-01T00:00:00Z'),
  make('one-shared-old', ['tax'], '2025-06-01T00:00:00Z'),
  make('none-newest', ['insurance'], '2026-06-01T00:00:00Z'),
  make('none-older', ['college'], '2026-03-01T00:00:00Z'),
];

describe('relatedArticles', () => {
  it('excludes the current article and orders by shared tags, then recency', () => {
    expect(relatedArticles(all, all[0]!).map((item) => item.slug)).toEqual([
      'two-shared-old',
      'one-shared-new',
      'one-shared-old',
    ]);
  });

  it('fills with the most recent unrelated articles when fewer than max share a tag', () => {
    const current = make('solo', ['insurance'], '2026-01-01T00:00:00Z');
    expect(relatedArticles(all, current).map((item) => item.slug)).toEqual([
      'none-newest',
      'current',
      'one-shared-new',
    ]);
  });

  it('respects max and returns [] when there is nothing else', () => {
    expect(relatedArticles(all, all[0]!, 1).map((item) => item.slug)).toEqual(['two-shared-old']);
    expect(relatedArticles([all[0]!], all[0]!)).toEqual([]);
  });
});
```

  `RelatedArticles/Component.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { RelatedArticles } from '.';

const items = [
  { slug: 'a', title: 'Article A', tags: ['retirement'], published_at: '2026-01-01T00:00:00Z' },
  { slug: 'b', title: 'Article B', tags: ['tax'], published_at: '2026-02-01T00:00:00Z' },
];

describe('RelatedArticles', () => {
  it('renders a labelled section with a card link per item', () => {
    render(<RelatedArticles items={items} />);

    const section = screen.getByRole('region', { name: 'Related articles' });
    expect(section).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Article A' })).toHaveAttribute('href', '/content/a');
    expect(screen.getByRole('link', { name: 'Article B' })).toHaveAttribute('href', '/content/b');
  });

  it('renders nothing for an empty list', () => {
    const { container } = render(<RelatedArticles items={[]} />);

    expect(container).toBeEmptyDOMElement();
  });
});
```

  Append to `ArticleScreen/Component.test.tsx` (its existing fixture gains `related`; the
  existing `render(<ArticleScreen article={…} />)` calls must pass `related={[]}` to type-check —
  that prop addition is the only permitted edit to existing tests):

```tsx
  it('renders the back link, tag links to the filter, the disclaimer as an info alert, and the chat CTA', () => {
    render(<ArticleScreen article={article} related={[]} />);

    expect(screen.getByRole('link', { name: /Back to articles/ })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: article.tags[0]! })).toHaveAttribute(
      'href',
      `/?tag=${encodeURIComponent(article.tags[0]!)}`,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('not financial advice');
    expect(screen.getByRole('link', { name: 'Ask a question about this topic' })).toHaveAttribute('href', '/chat');
  });

  it('renders related articles when given and omits the section when empty', () => {
    const related = [{ slug: 'r', title: 'Related One', tags: ['x'], published_at: '2026-01-01T00:00:00Z' }];
    const { unmount } = render(<ArticleScreen article={article} related={related} />);
    expect(screen.getByRole('region', { name: 'Related articles' })).toBeInTheDocument();
    unmount();

    render(<ArticleScreen article={article} related={[]} />);
    expect(screen.queryByRole('region', { name: 'Related articles' })).toBeNull();
  });
```

  (`article` = that file's existing detail fixture; if it is inline per test, lift it to a
  `const article` at the top — a non-behavioural refactor of the test file that the
  implementer is allowed to keep.)

- [ ] **Run RED:** `pnpm -C apps/client test -- related RelatedArticles ArticleScreen` → FAIL.

- [ ] **GREEN — implementer:** copy → `related.ts` → `publicApi` cache → `RelatedArticles` →
  `ArticleScreen` (+ interface) → page + loading `maxWidth="md"`. Type-check; full suite.

- [ ] **Screenshots:** `/content/medicare-enrollment-basics` at 1440 (md column, related cards
  in a row) and 390 (stacked). Iframe technique.

- [ ] **Gates:** `pnpm gates:client` → clean.

- [ ] **Commit:**
  `git add apps/client/src/lib/related.ts apps/client/src/lib/related.test.ts apps/client/src/lib/publicApi.ts apps/client/src/lib/copy.ts apps/client/src/components/content/ArticleScreen "apps/client/src/app/content/[slug]"`
  `git commit -m "feat(client): article reading layout, related articles, chat CTA (p8 t10)"`

## Verify

```bash
pnpm -C apps/client test -- related RelatedArticles ArticleScreen
pnpm gates:client
```

## Acceptance

- Article column is `md`; one h1; disclaimer is an `Alert`; related section only when non-empty;
  CTA links to `/chat`; `getContentBySlug` is `cache()`-wrapped.
- Pure helpers tested in node; screen tests by role/name.
