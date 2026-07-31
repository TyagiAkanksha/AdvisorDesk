// @vitest-environment jsdom
import { render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import type { ContentDto, ContentListDto } from '@/types/api/content';

import { ContentListScreen } from '.';

// fix round 1, F1 (C1: pagination UI was entirely missing — content past item 20 was
// unreachable). Exercises the new common/Pagination wiring end-to-end through
// ContentListScreen + useContentList's existing (previously untested — reviewer M3) page
// state, including the stale-page protections already in the hook
// (`setStatusAndResetPage` et al.).
//
// Request-aware fetch mocking (task-04 review lesson, mirrored from the pinned
// Component.test.tsx in this same folder): `fetchBaseQuery` hands the mocked `fetch` a native
// `Request`, which stringifies to `"[object Request]"` — resolve the real URL off the
// `Request` itself, not `String(input)`.
function requestUrl(input: RequestInfo | URL): string {
  return input instanceof Request ? input.url : String(input);
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return input instanceof Request ? input.method : (init?.method ?? 'GET');
}

function pathnameOf(input: RequestInfo | URL): string {
  return new URL(requestUrl(input)).pathname;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const itemA: ContentDto = {
  author_id: null,
  body_md: '# Roth IRA Conversion Basics',
  created_at: '2026-01-01T00:00:00Z',
  id: '11111111-1111-1111-1111-111111111111',
  published_at: null,
  slug: 'roth-ira-conversion-basics',
  status: 'draft',
  tags: [],
  title: 'Roth IRA Conversion Basics',
  updated_at: '2026-03-15T00:00:00Z',
  updated_by: null,
};

const itemB: ContentDto = {
  author_id: null,
  body_md: '# Estate Planning 101',
  created_at: '2025-12-01T00:00:00Z',
  id: '22222222-2222-2222-2222-222222222222',
  published_at: '2025-12-05T00:00:00Z',
  slug: 'estate-planning-101',
  status: 'published',
  tags: [],
  title: 'Estate Planning 101',
  updated_at: '2025-12-20T00:00:00Z',
  updated_by: null,
};

// A page-2 fixture with exactly one row — used to prove the delete flow on a page other than
// the first still issues the invalidation-driven refetch for THAT page's args.
const itemC: ContentDto = {
  author_id: null,
  body_md: '# Social Security Timing',
  created_at: '2025-11-01T00:00:00Z',
  id: '33333333-3333-3333-3333-333333333333',
  published_at: '2025-11-05T00:00:00Z',
  slug: 'social-security-timing',
  status: 'published',
  tags: [],
  title: 'Social Security Timing',
  updated_at: '2025-11-06T00:00:00Z',
  updated_by: null,
};

const page1Fixture: ContentListDto = {
  items: [itemA, itemB],
  page: 1,
  page_size: 20,
  total: 45,
};

const page2Fixture: ContentListDto = {
  items: [itemC],
  page: 2,
  page_size: 20,
  total: 21,
};

// After the sole page-2 row is deleted, a real API would answer page 2 with an empty page
// (total drops to 20 — exactly one page). `useContentList` does not itself navigate back to
// page 1 on this shrinkage (documented, not asserted as a requirement) — the UI's job is only
// to render that answer as an explicit EmptyState rather than a stale/blank screen.
const page2AfterDeleteFixture: ContentListDto = {
  items: [],
  page: 2,
  page_size: 20,
  total: 20,
};

function mockFetch(listHandler: (url: URL) => Response) {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
    async (input, init) => {
      const pathname = pathnameOf(input);
      const method = requestMethod(input, init);

      if (pathname === '/api/v1/content' && method === 'GET') {
        return listHandler(new URL(requestUrl(input)));
      }
      if (pathname.startsWith('/api/v1/content/') && method === 'DELETE') {
        return new Response(null, { status: 204 });
      }
      return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
    },
  );
  global.fetch = fetchMock;
  return fetchMock;
}

function renderScreen() {
  return render(
    <Providers>
      <ContentListScreen />
    </Providers>,
  );
}

type FetchMock = ReturnType<typeof mockFetch>;

function lastListCall(fetchMock: FetchMock) {
  const calls = fetchMock.mock.calls.filter(
    ([input, init]) =>
      pathnameOf(input) === '/api/v1/content' && requestMethod(input, init) === 'GET',
  );
  return calls.at(-1);
}

describe('ContentListScreen pagination', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the pager with the total and page count from the list fixture', async () => {
    mockFetch(() => jsonResponse(page1Fixture));

    renderScreen();
    await screen.findByRole('row', { name: new RegExp(itemA.title) });

    // 45 total / 20 per page -> 3 pages; "Showing 1-20 of 45" per common/Pagination.
    expect(screen.getByText('Showing 1–20 of 45')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Go to page 3' })).toBeInTheDocument();
  });

  it('clicking next page issues a GET request with page=2', async () => {
    const fetchMock = mockFetch((url) => {
      const page = url.searchParams.get('page');
      return jsonResponse(page === '2' ? page2Fixture : page1Fixture);
    });
    const user = userEvent.setup();

    renderScreen();
    await screen.findByRole('row', { name: new RegExp(itemA.title) });
    fetchMock.mockClear();

    await user.click(screen.getByRole('button', { name: 'Go to next page' }));

    await waitFor(() => {
      const call = lastListCall(fetchMock);
      expect(call).toBeDefined();
      const url = new URL(requestUrl(call![0]));
      expect(url.searchParams.get('page')).toBe('2');
    });
    await screen.findByRole('row', { name: new RegExp(itemC.title) });
  });

  it('changing a filter after paging forward resets the next request to page=1', async () => {
    const fetchMock = mockFetch((url) => {
      const page = url.searchParams.get('page');
      return jsonResponse(page === '2' ? page2Fixture : page1Fixture);
    });
    const user = userEvent.setup();

    renderScreen();
    await screen.findByRole('row', { name: new RegExp(itemA.title) });

    await user.click(screen.getByRole('button', { name: 'Go to next page' }));
    await screen.findByRole('row', { name: new RegExp(itemC.title) });
    fetchMock.mockClear();

    const statusFilter = screen.getByRole('combobox', { name: /status/i });
    await user.click(statusFilter);
    const publishedOption = await screen.findByRole('option', { name: /published/i });
    await user.click(publishedOption);

    await waitFor(() => {
      const call = lastListCall(fetchMock);
      expect(call).toBeDefined();
      const url = new URL(requestUrl(call![0]));
      expect(url.searchParams.get('page')).toBe('1');
      expect(url.searchParams.get('status')).toBe('published');
    });
  });

  it('deleting the sole row on page 2 leaves the pager mounted through the stranding refetch, with a working way back to page 1', async () => {
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
        return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
      },
    );
    global.fetch = fetchMock;
    const user = userEvent.setup();

    renderScreen();
    await screen.findByRole('row', { name: new RegExp(itemA.title) });
    await user.click(screen.getByRole('button', { name: 'Go to next page' }));
    await screen.findByRole('row', { name: new RegExp(itemC.title) });

    const deleteButton = screen.getByRole('button', {
      name: new RegExp(`delete.*${itemC.title}`, 'i'),
    });
    await user.click(deleteButton);
    const dialog = await screen.findByRole('dialog');
    const confirmButton = within(dialog).getByRole('button', { name: /delete/i });
    await user.click(confirmButton);

    // The DELETE fired, and the still-subscribed page-2 `listContent` query refetched (tag
    // invalidation, no manual refetch call) — landing behavior: EmptyState, not a stranded
    // stale row or a blank screen.
    await waitFor(() => {
      const calls = fetchMock.mock.calls.filter(
        ([input, init]) =>
          pathnameOf(input) === '/api/v1/content' &&
          requestMethod(input, init) === 'GET' &&
          new URL(requestUrl(input)).searchParams.get('page') === '2',
      );
      expect(calls.length).toBeGreaterThanOrEqual(2);
    });
    expect(await screen.findByRole('status')).toHaveTextContent(/no content found/i);

    // fix round 2, C2/I3: this is what "doesn't strand the UI" actually requires — the pager
    // (not just the EmptyState text) must still be mounted, offering a real way back. Before
    // the round-2 fix, ContentListScreen only rendered `<Pagination/>` inside the
    // `items.length>0` branch, so it unmounted along with the table here and this button did
    // not exist.
    const previousPageButton = screen.getByRole('button', { name: 'Go to previous page' });
    fetchMock.mockClear();
    await user.click(previousPageButton);

    await waitFor(() => {
      const call = lastListCall(fetchMock);
      expect(call).toBeDefined();
      const url = new URL(requestUrl(call![0]));
      expect(url.searchParams.get('page')).toBe('1');
    });
    await screen.findByRole('row', { name: new RegExp(itemA.title) });
  });
});
