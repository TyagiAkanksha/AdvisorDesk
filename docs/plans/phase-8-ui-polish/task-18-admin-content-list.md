---
id: p8-t18
phase: phase-8-ui-polish
depends_on: [p8-t15]
status: pending
spec: docs/plans/phase-8-ui-polish/DESIGN.md
review: opus
---

# Task 18 — Content list: URL-synced filters, MUI table, skeleton rows, two empty states (C4)

## Goal

The content list becomes a proper index screen: `PageHeader` with the "New content" action;
Status/Tag/Search filters whose state **lives in the URL** (`?status=&tag=&q=&page=`, so the
dashboard's stat cards and tag links deep-link into it and the browser back button works); a
"Clear filters" button; an outlined MUI table (title link · status chip · outlined tag chips ·
updated date · Edit/Delete icon buttons with tooltips) that scrolls horizontally on phones; five
skeleton rows while loading; two distinct empty states; automatic clamping of a stranded page
(WR-60); delete success feedback through the global snackbar (second `AppSnackbar` call site
retired).

## Context (read ONLY these)

- `docs/plans/phase-8-ui-polish/DESIGN.md` §2, §5 C4 (plan-time ruling: the "Showing 1–20 of
  31" count already lives in `common/Pagination` — it is NOT duplicated into the filter row).
- `docs/FRONTEND-CONVENTIONS.md` §3, §7, §9.
- `apps/admin/src/components/content/ContentListScreen/{Component.tsx, useContentList.ts,
  components/ContentTable/*, Component.test.tsx, pagination.test.tsx, newContentLink.test.tsx,
  deleteError.test.tsx, resilientRefetch.test.tsx}` — everything here is rewritten or
  migrated; every pin is listed below.
- `apps/admin/src/testing/nextNavigation.ts` (task 14 — the stateful seam every test in this
  folder switches to) and its own test for the usage idiom.
- `apps/admin/src/components/common/{PageHeader,Button,IconButton,Select,TextField,Stack,
  TableContainer,Table,TableHead,TableBody,TableRow,TableCell,Paper,Chip,Link,StatusChip,
  Skeleton,EmptyState,ErrorState,ConfirmDialog,Pagination,Tooltip}/`, `useSnackbar`.
- `apps/admin/src/lib/{format.ts, copy.ts, errorMessage.ts}`, `lib/api/{contentApi.ts, tagsApi.ts}`,
  `types/api/content.ts` (`ContentStatus` values).
- `apps/admin/src/app/(app)/content/page.tsx` (gains a `Suspense` boundary — see Interfaces).

## Files

**Create**
- `src/lib/contentListParams.ts`, `src/lib/contentListParams.test.ts`
- `src/components/content/ContentListScreen/useContentList.test.tsx`
- `src/components/content/ContentListScreen/components/ContentFilters/{Component.tsx, interface.ts, index.ts}`
- `src/components/content/ContentListScreen/components/ContentTableSkeleton/{Component.tsx, index.ts}`

**Modify**
- `src/components/content/ContentListScreen/{Component.tsx, useContentList.ts}`
- `src/components/content/ContentListScreen/components/ContentTable/{Component.tsx, interface.ts}`
- the five existing test files in `ContentListScreen/` (seam migration + the pins below)
- `src/app/(app)/content/page.tsx`
- `src/lib/copy.ts`

## Interfaces

```ts
// src/lib/copy.ts additions
// CONTENT_TITLE ('Content') already exists (task 15 — nav label = page title)
export const NEW_CONTENT_LABEL = 'New content';
export const CLEAR_FILTERS_LABEL = 'Clear filters';
export const CONTENT_TABLE_LABEL = 'Content';
export const NO_CONTENT_TITLE = 'No content yet';
export const NO_CONTENT_DESCRIPTION = 'Articles you create will show up here.';
export const CREATE_FIRST_ARTICLE_LABEL = 'Create your first article';
export const NO_MATCH_TITLE = 'No content matches these filters';
export const NO_MATCH_DESCRIPTION = 'Try a different status, tag or search term.';
export const CONTENT_LOAD_ERROR = "Couldn't load content.";
export const CONTENT_REFRESH_ERROR = "Couldn't refresh this list — showing the last loaded page.";
export const CONTENT_DELETED_MESSAGE = 'Deleted';
export const DELETE_ERROR_FALLBACK = "Couldn't delete this item. Please try again.";
export const EDIT_LABEL = 'Edit';      // tooltip here; the editor's phone toggle + Delete button reuse these (task 20)
export const DELETE_LABEL = 'Delete';

// src/lib/contentListParams.ts — pure
export interface ContentListParams {
  status: ContentStatus | '';
  tag: string;
  q: string;
  page: number; // ≥ 1
}
export const DEFAULT_CONTENT_LIST_PARAMS: ContentListParams; // { status: '', tag: '', q: '', page: 1 }
/** Unknown status values → ''; non-positive/non-integer page → 1; tag/q trimmed. */
export function parseContentListParams(search: URLSearchParams): ContentListParams;
/** '' when every field is default, else '?status=…&tag=…&q=…&page=…' (defaults omitted, that key order, URLSearchParams encoding). */
export function buildContentListSearch(params: ContentListParams): string;
export function hasActiveFilters(params: ContentListParams): boolean; // status || tag || q

// useContentList.ts — the URL is the single source of truth for status/tag/page/q; the search
// FIELD keeps a local echo (`q`) so typing is instant and the URL write is debounced 300 ms.
export interface UseContentListResult {
  items: ContentDto[];
  total: number;
  page: number;                 // from the URL (after clamping)
  pageSize: number;             // 20
  isLoading: boolean;
  isError: boolean;
  hasData: boolean;
  status: ContentStatus | '';
  setStatus: (status: ContentStatus | '') => void;   // writes URL, page → 1
  tag: string;
  setTag: (tag: string) => void;                     // writes URL, page → 1
  q: string;                                         // live field value
  setQ: (q: string) => void;                         // updates the field; URL write debounced 300 ms, page → 1
  hasFilters: boolean;
  clearFilters: () => void;                          // writes '' (all defaults) + clears the field
  setPage: (page: number) => void;                   // writes URL
  deleteContent: (id: string) => Promise<void>;      // success → useSnackbar().success(CONTENT_DELETED_MESSAGE); failure → deleteError + rethrow (unchanged)
  isDeleting: boolean;
  deleteError: string | null;
  clearDeleteError: () => void;
}
// Removed: refreshErrorMessage / dismissRefreshError → a background refetch failure (hasData &&
// isError, rising edge) calls useSnackbar().error(CONTENT_REFRESH_ERROR) once.
// URL writes: router.replace(`${pathname}${buildContentListSearch(next)}`, { scroll: false }).
// Clamp (WR-60): effect — when `data` is present and `page > max(1, ceil(total / pageSize))`, write page = that max.
// Debounce/sync (exact):
//   const [qInput, setQInput] = useState(params.q);
//   const lastWrittenQ = useRef(params.q);
//   useEffect(() => { if (params.q !== lastWrittenQ.current) { lastWrittenQ.current = params.q; setQInput(params.q); } }, [params.q]);
//   const paramsRef = useRef(params); paramsRef.current = params;   // live params for the timer
//   useEffect(() => {
//     if (qInput === params.q) return;
//     const timer = setTimeout(() => { lastWrittenQ.current = qInput; write({ ...paramsRef.current, q: qInput, page: 1 }); }, SEARCH_DEBOUNCE_MS);
//     return () => clearTimeout(timer);
//   }, [qInput, params.q]);   // the timer reads the LIVE params via the ref (t18 review I-1): a status/tag
//                             // change inside the debounce window must not be reverted by the pending q write
//   clearFilters = () => { lastWrittenQ.current = ''; setQInput(''); write(DEFAULT_CONTENT_LIST_PARAMS); };

// components/ContentFilters/interface.ts (dumb)
export interface ContentFiltersProps {
  status: ContentStatus | '';
  tag: string;
  q: string;
  tagOptions: SelectOption[];   // already includes { value: '', label: 'All tags' } first
  hasFilters: boolean;
  onStatusChange: (status: ContentStatus | '') => void;
  onTagChange: (tag: string) => void;
  onQChange: (q: string) => void;
  onClear: () => void;
}
// `Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 3, alignItems: { sm: 'center' } }}`:
// Select "Status" (options: All statuses + the three), Select "Tag", TextField "Search" (type="search",
// placeholder "Search by title…"), then `hasFilters ? <Button variant="text" onClick={onClear}>{CLEAR_FILTERS_LABEL}</Button> : null`.

// components/ContentTable/interface.ts — unchanged shape { items, onDeleteClick }; render becomes:
// <TableContainer component={Paper} variant="outlined" sx={{ overflowX: 'auto' }}>
//   <Table aria-label={CONTENT_TABLE_LABEL}>
//     head: Title | Status | Tags | Updated | Actions(align right)
//     row (`hover`): <Link href={`/content/${id}`}>{title}</Link> | <StatusChip/> |
//       <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap' }}>{tags.map(t => <Chip key size="small" variant="outlined" label={t}/>)}</Stack> |
//       {formatDate(updated_at)} |
//       <IconButton name="Edit" label={`Edit ${title}`} href={`/content/${id}`} size="small" tooltip={EDIT_LABEL}/>
//       <IconButton name="Delete" label={`Delete ${title}`} onClick size="small" tooltip={DELETE_LABEL}/>

// components/ContentTableSkeleton — zero-prop: the same TableContainer/Table head, then 5 rows of
// `Skeleton variant="text"` cells; root `role="status" aria-label={LOADING_LABEL}` on the container.
```

**Screen render (exact structure):**

```tsx
<Box>
  <PageHeader title={CONTENT_TITLE} actions={<Button href="/content/new" variant="contained">{NEW_CONTENT_LABEL}</Button>} />
  <ContentFilters … />
  {isLoading && !hasData ? <ContentTableSkeleton /> : null}
  {!hasData && isError ? <ErrorState message={CONTENT_LOAD_ERROR} /> : null}
  {hasData && items.length === 0 && !hasFilters ? (
    <EmptyState title={NO_CONTENT_TITLE} description={NO_CONTENT_DESCRIPTION}
      action={<Button href="/content/new" variant="contained">{CREATE_FIRST_ARTICLE_LABEL}</Button>} />
  ) : null}
  {hasData && items.length === 0 && hasFilters ? (
    <EmptyState icon="Search" title={NO_MATCH_TITLE} description={NO_MATCH_DESCRIPTION}
      action={<Button variant="outlined" onClick={clearFilters}>{CLEAR_FILTERS_LABEL}</Button>} />
  ) : null}
  {hasData && items.length > 0 ? <ContentTable items={items} onDeleteClick={handleDeleteClick} /> : null}
  {hasData && total > 0 ? <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} /> : null}
  <ConfirmDialog … destructive />   // as today, plus `destructive`
</Box>
```

**Page (exact):**

```tsx
import type { Metadata } from 'next';
import { Suspense } from 'react';

import { PageContainer } from '@/components/common';
import { ContentListScreen } from '@/components/content/ContentListScreen';
import { PageSkeleton } from '@/components/shell/PageSkeleton';

export const metadata: Metadata = { title: 'Content' };

// phase-8 task-18: the screen reads `useSearchParams()`; Next requires a Suspense boundary above
// any such client component on a statically prerendered route (build error otherwise).
export default function Page() {
  return (
    <PageContainer>
      <Suspense fallback={<PageSkeleton />}>
        <ContentListScreen />
      </Suspense>
    </PageContainer>
  );
}
```

## Steps (TDD)

- [ ] **RED — test-author.**

**Seam migration (all five existing files):** add at the top

```tsx
import { navigation } from '@/testing/nextNavigation';

vi.mock('next/navigation', () => import('@/testing/nextNavigation'));
```

and a `beforeEach(() => { navigation.reset('/content'); })` in each `describe`. Nothing else
changes in `newContentLink.test.tsx`, `deleteError.test.tsx`, `resilientRefetch.test.tsx`
(the latter's `findByRole('alert')` now finds the global snackbar — same role). In
`Component.test.tsx` the `mockFetch` helper must ALSO answer `GET /api/v1/tags` with `[]`
(the filters query tags; today's 404 fallthrough is tolerated but noisy).

**`pagination.test.tsx` pin rewrite** — replace the last test (`deleting the sole row on page
2 …`) with:

```tsx
  it('deleting the sole row on page 2 clamps the URL back to page 1 automatically (WR-60)', async () => {
    let deleteCount = 0;
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async (input, init) => {
        const pathname = pathnameOf(input);
        const method = requestMethod(input, init);

        if (pathname === '/api/v1/content' && method === 'GET') {
          const url = new URL(requestUrl(input));
          if (url.searchParams.get('page') !== '2') {
            return jsonResponse(page1Fixture);
          }
          return jsonResponse(deleteCount > 0 ? page2AfterDeleteFixture : page2Fixture);
        }
        if (pathname.startsWith('/api/v1/content/') && method === 'DELETE') {
          deleteCount += 1;
          return new Response(null, { status: 204 });
        }
        if (pathname === '/api/v1/tags') return jsonResponse([]);
        return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
      },
    );
    global.fetch = fetchMock;
    const user = userEvent.setup();

    renderScreen();
    await screen.findByRole('row', { name: new RegExp(itemA.title) });
    await user.click(screen.getByRole('button', { name: 'Go to next page' }));
    await screen.findByRole('row', { name: new RegExp(itemC.title) });
    expect(navigation.search).toBe('?page=2');

    await user.click(screen.getByRole('button', { name: new RegExp(`delete.*${itemC.title}`, 'i') }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: /delete/i }));

    // The page-2 refetch answers an empty page with total 20 → last page is 1 → the hook rewrites
    // the URL to page 1 and page 1's rows render — no stranded empty page, no manual "previous".
    await waitFor(() => expect(navigation.search).toBe(''));
    await screen.findByRole('row', { name: new RegExp(itemA.title) });
    expect(await screen.findByRole('status')).toHaveTextContent('Deleted');
  });
```

Also update this file's first test to assert the URL: after paging, add
`expect(navigation.replace).toHaveBeenLastCalledWith('/content?page=2', { scroll: false });`
to `clicking next page issues a GET request with page=2`; and in `changing a filter after
paging forward resets the next request to page=1` add
`expect(navigation.search).toBe('?status=published');` after the `waitFor`.

**Append to `Component.test.tsx`:**

```tsx
  it('renders the page header with the New content action', async () => {
    mockFetch(() => jsonResponse(twoItemFixture));

    renderScreen();

    expect(await screen.findByRole('heading', { level: 1, name: 'Content' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'New content' })).toHaveAttribute('href', '/content/new');
  });

  it('initialises the filters from the URL and requests with them', async () => {
    // (page parsing is pinned at hook level — a page=2 here would be clamped by the 2-item fixture)
    navigation.reset('/content?status=published&tag=retirement&q=estate');
    const fetchMock = mockFetch(() => jsonResponse(twoItemFixture));

    renderScreen();

    await waitFor(() => {
      const listCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          pathnameOf(input) === '/api/v1/content' && requestMethod(input, init) === 'GET',
      );
      expect(listCall).toBeDefined();
      const url = new URL(requestUrl(listCall![0]));
      expect(url.searchParams.get('status')).toBe('published');
      expect(url.searchParams.get('tag')).toBe('retirement');
      expect(url.searchParams.get('q')).toBe('estate');
      expect(url.searchParams.get('page')).toBe('1');
    });
    expect(screen.getByRole('combobox', { name: /status/i })).toHaveTextContent('Published');
    expect(screen.getByLabelText(/search/i)).toHaveValue('estate');
  });

  it('shows Clear filters only when a filter is set, and clearing rewrites the URL to /content', async () => {
    navigation.reset('/content?status=draft');
    mockFetch(() => jsonResponse(twoItemFixture));
    const user = userEvent.setup();

    renderScreen();

    await user.click(await screen.findByRole('button', { name: 'Clear filters' }));

    expect(navigation.replace).toHaveBeenLastCalledWith('/content', { scroll: false });
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Clear filters' })).not.toBeInTheDocument(),
    );
  });

  it('renders the "no content yet" empty state with a create link when there is nothing at all', async () => {
    mockFetch(() => jsonResponse(emptyFixture));

    renderScreen();

    // The loading skeleton is also `role="status"` — wait for the loaded state's own text.
    const status = await waitFor(() => {
      const element = screen.getByRole('status');
      expect(element).toHaveTextContent('No content yet');
      return element;
    });
    expect(within(status).getByRole('link', { name: 'Create your first article' })).toHaveAttribute(
      'href',
      '/content/new',
    );
  });

  it('renders the "no match" empty state with a Clear filters button when filters exclude everything', async () => {
    navigation.reset('/content?q=zzz');
    mockFetch(() => jsonResponse(emptyFixture));
    const user = userEvent.setup();

    renderScreen();

    const status = await waitFor(() => {
      const element = screen.getByRole('status');
      expect(element).toHaveTextContent('No content matches these filters');
      return element;
    });
    await user.click(within(status).getByRole('button', { name: 'Clear filters' }));
    expect(navigation.replace).toHaveBeenLastCalledWith('/content', { scroll: false });
  });

  it('shows five skeleton rows (labelled Loading) instead of a spinner while the first page loads', () => {
    global.fetch = vi.fn(() => new Promise<Response>(() => {}));

    renderScreen();

    const status = screen.getByRole('status', { name: 'Loading' });
    expect(within(status).getAllByRole('row')).toHaveLength(6); // header + 5
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  });

  it('each row has an Edit link to the editor and a Delete button, both with tooltips', async () => {
    mockFetch(() => jsonResponse(twoItemFixture));
    const user = userEvent.setup();

    renderScreen();

    const rowA = await screen.findByRole('row', { name: new RegExp(itemA.title) });
    expect(within(rowA).getByRole('link', { name: `Edit ${itemA.title}` })).toHaveAttribute(
      'href',
      `/content/${itemA.id}`,
    );
    await user.hover(within(rowA).getByRole('button', { name: `Delete ${itemA.title}` }));
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Delete');
  });

  it('renders tags as outlined chips and the updated date through lib/format', async () => {
    mockFetch(() => jsonResponse(twoItemFixture));

    renderScreen();

    const rowB = await screen.findByRole('row', { name: new RegExp(itemB.title) });
    const chip = within(rowB).getByText('estate-planning').closest('.MuiChip-root');
    expect(chip).toHaveClass('MuiChip-outlined');
    expect(within(rowB).getByText(formatDate(itemB.updated_at))).toBeInTheDocument();
  });
```

(`formatDate` imported from `@/lib/format`; `within` already imported.)

**`useContentList.test.tsx`** (hook-level; `Wrapper` = `Providers`)

```tsx
// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import { navigation } from '@/testing/nextNavigation';
import type { ContentListDto } from '@/types/api/content';

import { useContentList } from './useContentList';

vi.mock('next/navigation', () => import('@/testing/nextNavigation'));

function Wrapper({ children }: { children: ReactNode }) {
  return <Providers>{children}</Providers>;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

function requestUrl(input: RequestInfo | URL): string {
  return input instanceof Request ? input.url : String(input);
}

const emptyPage = (total: number, page: number): ContentListDto => ({ items: [], page, page_size: 20, total });

function mockList(handler: (url: URL) => ContentListDto) {
  const fetchMock = vi.fn<(input: RequestInfo | URL) => Promise<Response>>(async (input) => {
    const url = new URL(requestUrl(input));
    if (url.pathname === '/api/v1/content') return jsonResponse(handler(url));
    return jsonResponse({ error: { code: 'not_found', message: 'unmocked' } }, 404);
  });
  global.fetch = fetchMock;
  return fetchMock;
}

describe('useContentList — URL is the filter state', () => {
  beforeEach(() => {
    navigation.reset('/content');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('reads status/tag/q/page from the URL', () => {
    navigation.reset('/content?status=draft&tag=retirement&q=roth&page=3');
    mockList(() => emptyPage(100, 3));

    const { result } = renderHook(() => useContentList(), { wrapper: Wrapper });

    expect(result.current.status).toBe('draft');
    expect(result.current.tag).toBe('retirement');
    expect(result.current.q).toBe('roth');
    expect(result.current.page).toBe(3);
    expect(result.current.hasFilters).toBe(true);
  });

  it('setStatus writes the URL with the page reset', async () => {
    // total 40 → page 2 is valid, so the clamp effect stays out of this test's way.
    mockList((url) => emptyPage(40, Number(url.searchParams.get('page') ?? 1)));
    navigation.reset('/content?page=2');
    const { result } = renderHook(() => useContentList(), { wrapper: Wrapper });

    act(() => result.current.setStatus('published'));

    expect(navigation.replace).toHaveBeenLastCalledWith('/content?status=published', { scroll: false });
    await waitFor(() => expect(result.current.status).toBe('published'));
    expect(result.current.page).toBe(1);
  });

  it('setQ updates the field immediately and writes the URL after the debounce', async () => {
    mockList(() => emptyPage(0, 1));
    const { result } = renderHook(() => useContentList(), { wrapper: Wrapper });

    act(() => result.current.setQ('ro'));
    expect(result.current.q).toBe('ro');
    expect(navigation.replace).not.toHaveBeenCalled();
    act(() => result.current.setQ('roth'));

    await waitFor(
      () => expect(navigation.replace).toHaveBeenLastCalledWith('/content?q=roth', { scroll: false }),
      { timeout: 2000 },
    );
    expect(navigation.replace).toHaveBeenCalledTimes(1);
  });

  it('an external URL change (back button) updates the search field', async () => {
    mockList(() => emptyPage(0, 1));
    navigation.reset('/content?q=roth');
    const { result } = renderHook(() => useContentList(), { wrapper: Wrapper });
    expect(result.current.q).toBe('roth');

    act(() => navigation.reset('/content'));

    await waitFor(() => expect(result.current.q).toBe(''));
  });

  it('clearFilters writes /content and empties the field', async () => {
    mockList(() => emptyPage(0, 1));
    navigation.reset('/content?status=draft&q=roth');
    const { result } = renderHook(() => useContentList(), { wrapper: Wrapper });

    act(() => result.current.clearFilters());

    expect(navigation.replace).toHaveBeenLastCalledWith('/content', { scroll: false });
    await waitFor(() => expect(result.current.hasFilters).toBe(false));
    expect(result.current.q).toBe('');
  });

  it('clamps a stranded page to the last page once the total is known (WR-60)', async () => {
    navigation.reset('/content?page=5');
    mockList((url) => emptyPage(25, Number(url.searchParams.get('page') ?? 1)));

    renderHook(() => useContentList(), { wrapper: Wrapper });

    await waitFor(() =>
      expect(navigation.replace).toHaveBeenLastCalledWith('/content?page=2', { scroll: false }),
    );
  });

  it('never clamps below page 1 or when the page is valid', async () => {
    navigation.reset('/content?page=2');
    mockList(() => emptyPage(25, 2));

    const { result } = renderHook(() => useContentList(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.hasData).toBe(true));
    expect(navigation.replace).not.toHaveBeenCalled();
  });
});
```

**`src/lib/contentListParams.test.ts`** (node)

```ts
import { describe, expect, it } from 'vitest';

import {
  DEFAULT_CONTENT_LIST_PARAMS,
  buildContentListSearch,
  hasActiveFilters,
  parseContentListParams,
} from './contentListParams';

describe('contentListParams', () => {
  it('parses known values and falls back per field', () => {
    expect(parseContentListParams(new URLSearchParams('status=draft&tag= retirement &q=roth&page=3'))).toEqual({
      status: 'draft',
      tag: 'retirement',
      q: 'roth',
      page: 3,
    });
    expect(parseContentListParams(new URLSearchParams('status=bogus&page=0'))).toEqual(DEFAULT_CONTENT_LIST_PARAMS);
    expect(parseContentListParams(new URLSearchParams('page=abc'))).toEqual(DEFAULT_CONTENT_LIST_PARAMS);
    expect(parseContentListParams(new URLSearchParams('page=2.5'))).toEqual(DEFAULT_CONTENT_LIST_PARAMS);
    expect(parseContentListParams(new URLSearchParams(''))).toEqual(DEFAULT_CONTENT_LIST_PARAMS);
  });

  it('builds the search string with defaults omitted, in a fixed key order', () => {
    expect(buildContentListSearch(DEFAULT_CONTENT_LIST_PARAMS)).toBe('');
    expect(buildContentListSearch({ status: 'published', tag: '', q: '', page: 1 })).toBe('?status=published');
    expect(buildContentListSearch({ status: '', tag: 'a&b', q: 'roth ira', page: 2 })).toBe('?tag=a%26b&q=roth+ira&page=2');
  });

  it('round-trips', () => {
    const params = { status: 'archived' as const, tag: 'tax-planning', q: 'x', page: 4 };
    expect(parseContentListParams(new URLSearchParams(buildContentListSearch(params)))).toEqual(params);
  });

  it('hasActiveFilters ignores the page', () => {
    expect(hasActiveFilters({ ...DEFAULT_CONTENT_LIST_PARAMS, page: 3 })).toBe(false);
    expect(hasActiveFilters({ ...DEFAULT_CONTENT_LIST_PARAMS, q: 'x' })).toBe(true);
  });
});
```

- [ ] **Run RED:** `pnpm -C apps/admin test -- ContentListScreen contentListParams` →
  `lib/contentListParams` unresolved; `useContentList.test` fails on missing `hasFilters`/
  `clearFilters` and URL writes; the appended screen cases and the rewritten pagination pin
  fail; the migrated files' existing cases stay green (they only gained the seam).

- [ ] **GREEN — implementer:** copy → `contentListParams.ts` → `useContentList.ts` per the
  exact debounce/clamp notes → `ContentFilters` → `ContentTable` → `ContentTableSkeleton` →
  screen → page `Suspense`. Delete flow keeps today's error handling and adds the success
  notice.

- [ ] **Run GREEN:** `pnpm -C apps/admin test`; `pnpm -C apps/admin type-check`.

- [ ] **Screenshots** (iframe technique, 1440 + 390, real screen with the local API's seed
  data, signed in): `/content` with rows; `/content?status=published`; `/content?q=zzz` (no
  match); phone view showing the horizontally scrolling table container. Store as
  `t18-content-*.jpg`.

- [ ] **Gates:** `pnpm gates:admin` → clean; `pnpm -C apps/admin build` → exit 0 (proves the
  `Suspense` boundary satisfies Next's `useSearchParams` bailout — without it the build fails
  with "Missing Suspense boundary with useSearchParams").

- [ ] **Commit:**
  `git add apps/admin/src/components/content/ContentListScreen apps/admin/src/lib/contentListParams.ts apps/admin/src/lib/contentListParams.test.ts apps/admin/src/lib/copy.ts "apps/admin/src/app/(app)/content/page.tsx"`
  `git commit -m "feat(admin): content list — URL-synced filters, MUI table, skeleton rows, empty states (p8 t18)"`

## Verify

```bash
pnpm -C apps/admin test -- ContentListScreen contentListParams
pnpm gates:admin && pnpm -C apps/admin build
```

## Acceptance

- `/content?status=draft` (from a stat card) and `/content?tag=x` (from the tag table) open
  pre-filtered; changing filters rewrites the URL; back button restores the field; Clear
  filters resets to `/content`; a stranded page clamps automatically.
- MUI table with links/chips/dates/tooltipped icon buttons; skeleton rows; two empty states;
  destructive confirm; "Deleted" success notice; refresh failure via the global snackbar.
- No `AppSnackbar` import remains in `ContentListScreen`; build green with the Suspense page.
