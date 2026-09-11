// @vitest-environment jsdom
import { render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import { formatDate } from '@/lib/format';
import { navigation } from '@/testing/nextNavigation';
import type { ContentDto, ContentListDto } from '@/types/api/content';

import { ContentListScreen } from '.';

vi.mock('next/navigation', () => import('@/testing/nextNavigation'));

// task-05 / PRD §2.2, §5.2: the content-list screen renders rows (title/status/tags/updated),
// empty/error states, a delete flow gated by a permanence-worded ConfirmDialog, and filter/search
// interactions that re-query the list. Mock ONLY the network edge (docs/FRONTEND-CONVENTIONS.md
// §7); drive the delete/filter interactions with `user-event`, not mocked callbacks.
//
// Request-aware fetch mocking (task-04 review lesson): `fetchBaseQuery` hands the mocked
// `fetch` a native `Request`, which stringifies to `"[object Request]"` — resolve the real URL
// off the `Request` itself, not `String(input)`.
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
  tags: ['tax-planning'],
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
  tags: ['estate-planning', 'retirement'],
  title: 'Estate Planning 101',
  updated_at: '2025-12-20T00:00:00Z',
  updated_by: null,
};

const twoItemFixture: ContentListDto = {
  items: [itemA, itemB],
  page: 1,
  page_size: 20,
  total: 2,
};

const emptyFixture: ContentListDto = {
  items: [],
  page: 1,
  page_size: 20,
  total: 0,
};

// `listHandler` lets each test control what `GET /content` answers (a fixed fixture, or an
// error) while still driving `DELETE /content/{id}` through the same mock.
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
      if (pathname === '/api/v1/tags' && method === 'GET') {
        return jsonResponse([]);
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

describe('ContentListScreen', () => {
  beforeEach(() => {
    navigation.reset('/content');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders each row with title, status, tags, and updated date from a 2-item list fixture', async () => {
    mockFetch(() => jsonResponse(twoItemFixture));

    renderScreen();

    const rowA = await screen.findByRole('row', { name: new RegExp(itemA.title) });
    expect(within(rowA).getByText(itemA.title)).toBeInTheDocument();
    // StatusChip text.
    expect(within(rowA).getByText(/draft/i)).toBeInTheDocument();
    for (const tag of itemA.tags) {
      expect(within(rowA).getByText(tag)).toBeInTheDocument();
    }
    // Updated date visible — not pinning an exact format, just that the fixture's
    // `updated_at` year is rendered somewhere in the row.
    expect(rowA.textContent).toContain('2026');

    const rowB = await screen.findByRole('row', { name: new RegExp(itemB.title) });
    expect(within(rowB).getByText(itemB.title)).toBeInTheDocument();
    expect(within(rowB).getByText(/published/i)).toBeInTheDocument();
    for (const tag of itemB.tags) {
      expect(within(rowB).getByText(tag)).toBeInTheDocument();
    }
    expect(rowB.textContent).toContain('2025');
  });

  it('shows EmptyState with visible, non-empty text and no item rows for an empty list fixture', async () => {
    mockFetch(() => jsonResponse(emptyFixture));

    renderScreen();

    // The loading skeleton is also `role="status"` — wait for the loaded state's own text.
    const status = await waitFor(() => {
      const element = screen.getByRole('status');
      expect(element).toHaveTextContent('No content yet');
      return element;
    });
    expect(status.textContent?.trim().length).toBeGreaterThan(0);
    expect(screen.queryByText(itemA.title)).not.toBeInTheDocument();
  });

  it('shows ErrorState with visible, non-empty error text when GET /content fails', async () => {
    global.fetch = vi.fn(async () =>
      jsonResponse({ error: { code: 'internal_error', message: 'Database is unreachable.' } }, 500),
    );

    renderScreen();

    // Visible surface only (an alert region with *some* text) — never ErrorState's internals
    // and never the raw API error body (FRONTEND-CONVENTIONS.md §9).
    const alert = await screen.findByRole('alert');
    expect(alert).toBeVisible();
    expect(alert.textContent?.trim().length).toBeGreaterThan(0);
  });

  it('deleting a row: Delete opens a permanent/no-restore ConfirmDialog, and confirming issues the DELETE', async () => {
    const fetchMock = mockFetch(() => jsonResponse(twoItemFixture));
    const user = userEvent.setup();

    renderScreen();

    // Icon-only row actions get an accessible name (FRONTEND-CONVENTIONS.md §9) — contract
    // pinned here: "Delete {title}".
    const deleteButton = await screen.findByRole('button', {
      name: new RegExp(`delete.*${itemA.title}`, 'i'),
    });
    await user.click(deleteButton);

    const dialog = await screen.findByRole('dialog');
    // PRD §2.2/§5.2/§12: deletion is permanent, no restore — the confirm copy must say so.
    expect(dialog).toHaveTextContent(/permanent/i);
    expect(dialog).toHaveTextContent(/no restore/i);

    const confirmButton = within(dialog).getByRole('button', { name: /delete/i });
    await user.click(confirmButton);

    await waitFor(() => {
      const deleteCall = fetchMock.mock.calls.find(
        ([input, init]) => requestMethod(input, init) === 'DELETE',
      );
      expect(deleteCall).toBeDefined();
      expect(pathnameOf(deleteCall![0])).toBe(`/api/v1/content/${itemA.id}`);
    });
  });

  it('selecting a status filter re-queries the list with that status param', async () => {
    const fetchMock = mockFetch(() => jsonResponse(twoItemFixture));
    const user = userEvent.setup();

    renderScreen();
    await screen.findByRole('row', { name: new RegExp(itemA.title) });
    fetchMock.mockClear();

    const statusFilter = screen.getByRole('combobox', { name: /status/i });
    await user.click(statusFilter);
    const publishedOption = await screen.findByRole('option', { name: /published/i });
    await user.click(publishedOption);

    await waitFor(() => {
      const listCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          pathnameOf(input) === '/api/v1/content' && requestMethod(input, init) === 'GET',
      );
      expect(listCall).toBeDefined();
      const url = new URL(requestUrl(listCall![0]));
      expect(url.searchParams.get('status')).toBe('published');
    });
  });

  // Search is debounced (useContentList, task-05 Interfaces). No fixed debounce value is
  // implemented yet to pin exactly — this test assumes ~300ms (documented in the test-author
  // report as a resolved ambiguity for the controller/implementer to confirm) and uses a real
  // timer + a generous `waitFor` timeout rather than fake timers, since fake timers interact
  // poorly with `user-event`'s own internal async scheduling and RTK Query's promise-based
  // dedupe/caching machinery.
  it('typing in the search field (debounced) re-queries the list with the q param', async () => {
    const fetchMock = mockFetch(() => jsonResponse(twoItemFixture));
    const user = userEvent.setup();

    renderScreen();
    await screen.findByRole('row', { name: new RegExp(itemA.title) });
    fetchMock.mockClear();

    const searchInput = screen.getByLabelText(/search/i);
    await user.type(searchInput, 'roth');

    await waitFor(
      () => {
        const listCall = fetchMock.mock.calls.find(
          ([input, init]) =>
            pathnameOf(input) === '/api/v1/content' && requestMethod(input, init) === 'GET',
        );
        expect(listCall).toBeDefined();
        const url = new URL(requestUrl(listCall![0]));
        expect(url.searchParams.get('q')).toBe('roth');
      },
      { timeout: 2000 },
    );
  });

  it('renders the page header with the New content action', async () => {
    mockFetch(() => jsonResponse(twoItemFixture));

    renderScreen();

    expect(await screen.findByRole('heading', { level: 1, name: 'Content' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'New content' })).toHaveAttribute(
      'href',
      '/content/new',
    );
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

    // The loading skeleton is also `role="status"` — `findByRole('status')` would resolve on it
    // and hand back a node React later unmounts; wait for the loaded state's own text instead.
    const status = await waitFor(() => {
      const element = screen.getByRole('status');
      expect(element).toHaveTextContent('No content yet');
      return element;
    });
    expect(screen.getByRole('link', { name: 'Create your first article' })).toHaveAttribute(
      'href',
      '/content/new',
    );
    expect(within(status).queryByRole('link')).toBeNull();
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
    expect(within(status).queryByRole('button')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Clear filters' }));
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
});
