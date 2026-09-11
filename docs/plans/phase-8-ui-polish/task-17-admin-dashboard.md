---
id: p8-t17
phase: phase-8-ui-polish
depends_on: [p8-t15]
status: done
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: sonnet
---

# Task 17 — Dashboard: linked stat cards, tag table, recent content (C3)

## Goal

Turn the dashboard's raw `<h2>/<p>` boxes into a real overview: `PageHeader`, three linked
`StatCard`s (Draft / Published / Archived → the filtered content list), and two outlined panels
at `md`+ — **Content by tag** (a table whose tag names link to `/content?tag=…`) and **Recent
content** (five rows from the content list: title link · status chip · updated date). A
labelled skeleton replaces the spinner; the background-refresh warning moves to the global
snackbar (first `AppSnackbar` call site retired).

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §2, §5 C3 (plan-time ruling: the second panel is
  titled **Recent content**, not "Recently updated" — the list endpoint orders by
  `created_at desc` and §7 rules out new API params).
- `docs/FRONTEND-CONVENTIONS.md` §3, §7, §9.
- `apps/admin/src/components/dashboard/DashboardScreen/{Component.tsx, useDashboardStats.ts,
  Component.test.tsx, resilientRefetch.test.tsx, components/TagCounts/*}` — replaced/rewritten
  here (pins listed below).
- `apps/admin/src/components/common/{PageHeader,StatCard,Grid,Paper,Table,TableHead,TableBody,
  TableRow,TableCell,Link,StatusChip,Skeleton,Typography,Box,EmptyState,ErrorState}/`,
  `common/SnackbarProvider` (`useSnackbar`).
- `apps/admin/src/lib/api/{statsApi.ts, contentApi.ts}` (`useListContentQuery({ page, page_size })`),
  `apps/admin/src/lib/format.ts` (task 14), `apps/admin/src/lib/copy.ts`,
  `apps/admin/src/types/api/{stats.ts, content.ts}`.
- `apps/admin/src/components/shell/PageSkeleton/Component.tsx` — the `role="status"
  aria-label={LOADING_LABEL}` skeleton idiom.

## Files

**Create**
- `src/components/dashboard/DashboardScreen/useDashboard.ts` (replaces `useDashboardStats.ts`)
- `src/components/dashboard/DashboardScreen/components/TagTable/{Component.tsx, interface.ts, index.ts, Component.test.tsx}`
- `src/components/dashboard/DashboardScreen/components/RecentContent/{Component.tsx, interface.ts, index.ts, Component.test.tsx}`
- `src/components/dashboard/DashboardScreen/components/DashboardSkeleton/{Component.tsx, index.ts}`

**Delete**
- `src/components/dashboard/DashboardScreen/useDashboardStats.ts`
- `src/components/dashboard/DashboardScreen/components/TagCounts/` (whole folder, incl. its test)

**Modify**
- `src/components/dashboard/DashboardScreen/Component.tsx`
- `src/components/dashboard/DashboardScreen/Component.test.tsx` (pins rewritten — see RED)
- `src/components/dashboard/DashboardScreen/resilientRefetch.test.tsx` (mock gains the
  `/api/v1/content` route; assertions unchanged)
- `src/lib/copy.ts`

## Interfaces

```ts
// src/lib/copy.ts additions
// DASHBOARD_TITLE ('Dashboard') already exists (task 15 — nav label = page title)
export const CONTENT_BY_TAG_TITLE = 'Content by tag';
export const RECENT_CONTENT_TITLE = 'Recent content';
export const NO_TAGS_MESSAGE = 'No tags yet.';
export const NO_RECENT_CONTENT_MESSAGE = 'No content yet.';
export const DASHBOARD_LOAD_ERROR = "Couldn't load the dashboard stats.";
export const DASHBOARD_REFRESH_ERROR = "Couldn't refresh the dashboard — showing the last loaded data.";
export const RECENT_CONTENT_LOAD_ERROR = "Couldn't load recent content.";

// useDashboard.ts
export interface TagRow { tag: string; count: number }
export interface UseDashboardResult {
  stats: StatsDto | undefined;
  /** `stats.by_tag` as rows, sorted by count desc then tag asc. Empty while `stats` is undefined. */
  tagRows: TagRow[];
  recent: ContentDto[] | undefined;      // `listContent({ page: 1, page_size: 5 }).items`
  recentFailed: boolean;                 // recent query errored with nothing cached
  isLoading: boolean;                    // stats pending with nothing cached
  loadFailed: boolean;                   // stats errored with nothing cached
}
export function useDashboard(): UseDashboardResult;
// Background refresh failure (stats cached AND isError) → `useSnackbar().error(DASHBOARD_REFRESH_ERROR)`
// fired ONCE per failure episode: an effect on the boolean `stats !== undefined && isError`
// that calls `error()` when it flips false → true. No dismiss state needed (the provider owns it).

// components/TagTable/interface.ts
export interface TagTableProps { rows: TagRow[] }
// renders `<Table size="small" aria-label={CONTENT_BY_TAG_TITLE}>`: head "Tag" | "Count"; each row:
// `<Link href={`/content?tag=${encodeURIComponent(tag)}`}>{tag}</Link>` | count. Empty → `<EmptyState message={NO_TAGS_MESSAGE} />`.

// components/RecentContent/interface.ts
export interface RecentContentProps { items: ContentDto[] }
// `<Table size="small" aria-label={RECENT_CONTENT_TITLE}>`: head "Title" | "Status" | "Updated"; row:
// `<Link href={`/content/${item.id}`}>{item.title}</Link>` | `<StatusChip status />` | `formatDate(item.updated_at)`.
// Empty → `<EmptyState message={NO_RECENT_CONTENT_MESSAGE} />`.

// components/DashboardSkeleton — zero-prop: `<Box role="status" aria-label={LOADING_LABEL}>` with the
// same Grid as the screen: three `Skeleton variant="rectangular" height={92}` (xs 12 / sm 4) and two
// `height={240}` (xs 12 / md 6).
```

**Screen render (exact structure):**

```tsx
const { stats, tagRows, recent, recentFailed, isLoading, loadFailed } = useDashboard();
if (isLoading) return <DashboardSkeleton />;
if (loadFailed || !stats) return <ErrorState message={DASHBOARD_LOAD_ERROR} />;
return (
  <Box>
    <PageHeader title={DASHBOARD_TITLE} />
    <Grid container spacing={2}>
      {STATUSES.map((status) => (
        <Grid key={status} size={{ xs: 12, sm: 4 }}>
          <StatCard label={CONTENT_STATUS_LABELS[status]} value={stats.by_status[status] ?? 0} href={`/content?status=${status}`} />
        </Grid>
      ))}
      <Grid size={{ xs: 12, md: 6 }}>
        <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
          <Typography variant="h5" component="h2" sx={{ mb: 1.5 }}>{CONTENT_BY_TAG_TITLE}</Typography>
          <TagTable rows={tagRows} />
        </Paper>
      </Grid>
      <Grid size={{ xs: 12, md: 6 }}>
        <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
          <Typography variant="h5" component="h2" sx={{ mb: 1.5 }}>{RECENT_CONTENT_TITLE}</Typography>
          {recentFailed ? <ErrorState message={RECENT_CONTENT_LOAD_ERROR} /> : null}
          {recent ? <RecentContent items={recent} /> : null}
          {!recent && !recentFailed ? <Skeleton variant="rectangular" height={160} /> : null}
        </Paper>
      </Grid>
    </Grid>
  </Box>
);
```

## Steps (TDD)

- [ ] **RED — test-author.** Rewrite `DashboardScreen/Component.test.tsx`'s three pins as
  below (keep `requestUrl`/`jsonResponse`/`renderScreen`; the fetch mock now also answers
  `GET /api/v1/content`), add the four new cases, write the two leaf tests, and add the
  `/api/v1/content` route to `resilientRefetch.test.tsx`'s mock (return `recentFixture`
  below; its assertions do not change — say so in the report). Delete
  `components/TagCounts/Component.test.tsx` together with the folder in GREEN (the
  test-author leaves the folder; the RED run reports it still green).

```tsx
// Component.test.tsx — fixtures + mock
import type { ContentDto, ContentListDto } from '@/types/api/content';
import { formatDate } from '@/lib/format';

const statsFixture = {
  by_status: { draft: 3, published: 5, archived: 1 },
  by_tag: { 'tax-planning': 2, retirement: 1 },
};

const itemA: ContentDto = {
  author_id: null,
  body_md: '# Roth IRA Conversion Basics',
  created_at: '2026-01-01T12:00:00Z',
  id: '11111111-1111-1111-1111-111111111111',
  published_at: null,
  slug: 'roth-ira-conversion-basics',
  status: 'draft',
  tags: ['tax-planning'],
  title: 'Roth IRA Conversion Basics',
  updated_at: '2026-03-15T12:00:00Z',
  updated_by: null,
};

const recentFixture: ContentListDto = { items: [itemA], page: 1, page_size: 5, total: 1 };

function mockFetch(overrides: { stats?: unknown; recent?: ContentListDto } = {}) {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
    async (input) => {
      const url = new URL(requestUrl(input));
      if (url.pathname === '/api/v1/stats') return jsonResponse(overrides.stats ?? statsFixture);
      if (url.pathname === '/api/v1/content') return jsonResponse(overrides.recent ?? recentFixture);
      return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
    },
  );
  global.fetch = fetchMock;
  return fetchMock;
}
```

```tsx
  it('renders one linked stat card per status, each pointing at the filtered content list', async () => {
    mockFetch();

    renderScreen();

    const draft = await screen.findByRole('link', { name: /^Draft\s*3$/ });
    expect(draft).toHaveAttribute('href', '/content?status=draft');
    expect(screen.getByRole('link', { name: /^Published\s*5$/ })).toHaveAttribute(
      'href',
      '/content?status=published',
    );
    expect(screen.getByRole('link', { name: /^Archived\s*1$/ })).toHaveAttribute(
      'href',
      '/content?status=archived',
    );
  });

  it('renders the tag table sorted by count, each tag linking to the tag-filtered list', async () => {
    mockFetch();

    renderScreen();

    const table = await screen.findByRole('table', { name: 'Content by tag' });
    const rows = within(table).getAllByRole('row').slice(1); // skip the header row
    expect(rows).toHaveLength(2);
    expect(within(rows[0]!).getByRole('link', { name: 'tax-planning' })).toHaveAttribute(
      'href',
      '/content?tag=tax-planning',
    );
    expect(within(rows[0]!).getByRole('cell', { name: '2' })).toBeInTheDocument();
    expect(within(rows[1]!).getByRole('link', { name: 'retirement' })).toHaveAttribute(
      'href',
      '/content?tag=retirement',
    );
  });

  it('renders recent content with a title link, status chip and formatted updated date', async () => {
    const fetchMock = mockFetch();

    renderScreen();

    const table = await screen.findByRole('table', { name: 'Recent content' });
    const row = within(table).getByRole('row', { name: new RegExp(itemA.title) });
    expect(within(row).getByRole('link', { name: itemA.title })).toHaveAttribute(
      'href',
      `/content/${itemA.id}`,
    );
    expect(within(row).getByText('Draft')).toBeInTheDocument();
    expect(within(row).getByText(formatDate(itemA.updated_at))).toBeInTheDocument();

    const listCall = fetchMock.mock.calls.find(
      ([input]) => new URL(requestUrl(input)).pathname === '/api/v1/content',
    );
    expect(new URL(requestUrl(listCall![0])).searchParams.get('page_size')).toBe('5');
  });

  it('shows a labelled skeleton (not a spinner) while GET /stats is pending', () => {
    global.fetch = vi.fn(() => new Promise<Response>(() => {}));

    renderScreen();

    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  });

  it('renders ErrorState with visible, non-empty error text when GET /stats fails', async () => {
    global.fetch = vi.fn(async () =>
      jsonResponse({ error: { code: 'internal_error', message: 'Database is unreachable.' } }, 500),
    );

    renderScreen();

    const alert = await screen.findByRole('alert');
    expect(alert).toBeVisible();
    expect(alert.textContent?.trim().length).toBeGreaterThan(0);
  });

  it('shows the empty messages when there are no tags and no content', async () => {
    mockFetch({
      stats: { by_status: {}, by_tag: {} },
      recent: { items: [], page: 1, page_size: 5, total: 0 },
    });

    renderScreen();

    expect(await screen.findByText('No tags yet.')).toBeInTheDocument();
    expect(screen.getByText('No content yet.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /^Draft\s*0$/ })).toBeInTheDocument();
  });

  it('a failed recent-content request shows an inline error but keeps the stat cards', async () => {
    global.fetch = vi.fn<(input: RequestInfo | URL) => Promise<Response>>(async (input) => {
      const url = new URL(requestUrl(input));
      if (url.pathname === '/api/v1/stats') return jsonResponse(statsFixture);
      return jsonResponse({ error: { code: 'internal_error', message: 'boom' } }, 500);
    });

    renderScreen();

    expect(await screen.findByRole('link', { name: /^Draft\s*3$/ })).toBeInTheDocument();
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't load recent content.");
  });
```

**`components/TagTable/Component.test.tsx`**

```tsx
// @vitest-environment jsdom
import { render, screen, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { describe, expect, it } from 'vitest';

import { TagTable } from '.';

describe('TagTable', () => {
  it('renders a linked row per tag with its count', () => {
    render(<TagTable rows={[{ tag: 'tax-planning', count: 2 }, { tag: 'retirement', count: 1 }]} />);

    const table = screen.getByRole('table', { name: 'Content by tag' });
    expect(within(table).getByRole('link', { name: 'tax-planning' })).toHaveAttribute(
      'href',
      '/content?tag=tax-planning',
    );
    expect(within(table).getByRole('cell', { name: '2' })).toBeInTheDocument();
    expect(within(table).getByRole('link', { name: 'retirement' })).toBeInTheDocument();
  });

  it('URL-encodes tag names in the link', () => {
    render(<TagTable rows={[{ tag: 'a&b', count: 1 }]} />);

    expect(screen.getByRole('link', { name: 'a&b' })).toHaveAttribute('href', '/content?tag=a%26b');
  });

  it('renders a quiet empty state for no rows', () => {
    render(<TagTable rows={[]} />);

    expect(screen.getByRole('status')).toHaveTextContent('No tags yet.');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });
});
```

**`components/RecentContent/Component.test.tsx`** (props-driven; `itemA` as above plus:)

```tsx
const itemB: ContentDto = {
  author_id: null,
  body_md: '# Estate Planning 101',
  created_at: '2025-12-01T12:00:00Z',
  id: '22222222-2222-2222-2222-222222222222',
  published_at: '2025-12-05T12:00:00Z',
  slug: 'estate-planning-101',
  status: 'published',
  tags: ['estate-planning', 'retirement'],
  title: 'Estate Planning 101',
  updated_at: '2025-12-20T12:00:00Z',
  updated_by: null,
};
```

```tsx
  it('renders title links, status chips and formatted dates', () => {
    render(<RecentContent items={[itemA, itemB]} />);

    const table = screen.getByRole('table', { name: 'Recent content' });
    const rowA = within(table).getByRole('row', { name: new RegExp(itemA.title) });
    expect(within(rowA).getByRole('link', { name: itemA.title })).toHaveAttribute('href', `/content/${itemA.id}`);
    expect(within(rowA).getByText('Draft')).toBeInTheDocument();
    expect(within(rowA).getByText(formatDate(itemA.updated_at))).toBeInTheDocument();
    const rowB = within(table).getByRole('row', { name: new RegExp(itemB.title) });
    expect(within(rowB).getByText('Published')).toBeInTheDocument();
  });

  it('renders the empty message for no items', () => {
    render(<RecentContent items={[]} />);

    expect(screen.getByRole('status')).toHaveTextContent('No content yet.');
  });
```

- [ ] **Run RED:** `pnpm -C apps/admin test -- DashboardScreen TagTable RecentContent` →
  leaf barrels unresolved; the rewritten screen cases fail (no links/tables/skeleton; the
  ErrorState case alone stays green); `resilientRefetch` stays green (mock addition only).

- [ ] **GREEN — implementer:** copy → `useDashboard.ts` (delete `useDashboardStats.ts`) →
  `TagTable` (delete `TagCounts/`) → `RecentContent` → `DashboardSkeleton` → screen.
  `tagRows` sort: `count` desc, then `tag` asc (`localeCompare`).

- [ ] **Run GREEN:** `pnpm -C apps/admin test`; `pnpm -C apps/admin type-check`.

- [ ] **Screenshots** (iframe technique, 1440 + 390): the dashboard with real data from the
  local API (sign in through the dev admin at `http://localhost:3001` with the allowlisted
  account, or reuse the throwaway `(app)/__shell` route idea from task 15 rendering
  `<DashboardScreen/>` behind a fetch mock is NOT acceptable — the screenshot must come from the
  real screen with the local API's seed data). Store as `t17-dashboard-{1440,390}.jpg`.

- [ ] **Gates:** `pnpm gates:admin` → clean.

- [ ] **Commit:**
  `git add apps/admin/src/components/dashboard apps/admin/src/lib/copy.ts`
  `git commit -m "feat(admin): dashboard — linked stat cards, tag table, recent content (p8 t17)"`

## Verify

```bash
pnpm -C apps/admin test -- DashboardScreen TagTable RecentContent
pnpm gates:admin
```

## Acceptance

- Three linked stat cards; tag table and recent table with links; skeleton while loading;
  `ErrorState` only when nothing is cached; recent-content failure is inline.
- `AppSnackbar` no longer imported by the dashboard (background refresh → `useSnackbar().error`).
- `TagCounts` and `useDashboardStats` gone; no `<h2>`/`<p>` raw tags remain in the dashboard.
