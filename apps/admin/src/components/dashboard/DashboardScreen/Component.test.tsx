// @vitest-environment jsdom
import { render, screen, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import { formatDate } from '@/lib/format';
import type { ContentDto, ContentListDto } from '@/types/api/content';

import { DashboardScreen } from '.';

// task-17 (DESIGN.md §2, §5 C3): the dashboard renders linked stat cards, a "Content by tag"
// table and a "Recent content" table built from `GET /stats` + `GET /api/v1/content`. Mock
// ONLY the network edge (docs/FRONTEND-CONVENTIONS.md §7); DashboardScreen, statsApi,
// contentApi, baseApi, the store, and Providers are all real, unmocked modules.
//
// Request-aware fetch mocking (task-04 review lesson, mirrored from RequireSession/AppShell
// Component.test.tsx): `fetchBaseQuery` hands the mocked `fetch` a native `Request`, which
// stringifies to `"[object Request]"` — resolve the real URL off the `Request` itself.
function requestUrl(input: RequestInfo | URL): string {
  return input instanceof Request ? input.url : String(input);
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

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

// phase-9 task-19 (RED): two groups — one 👎, one refused — matching the shape
// `GET /api/v1/weak-queries` will answer with once the route exists (it doesn't yet).
const weakQueriesFixture = {
  threshold: 0.5,
  days: 7,
  count: 2,
  items: [
    {
      normalized_question: 'does the firm cover crypto rsus',
      count: 2,
      kinds: ['negative_feedback'],
      worst_top_similarity: 0.6,
      examples: [],
    },
    {
      normalized_question: 'anything on qsbs',
      count: 1,
      kinds: ['refused'],
      worst_top_similarity: null,
      examples: [],
    },
  ],
};

function mockFetch(
  overrides: { stats?: unknown; recent?: ContentListDto; weakQueries?: unknown } = {},
) {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
    async (input) => {
      const url = new URL(requestUrl(input));
      if (url.pathname === '/api/v1/stats') return jsonResponse(overrides.stats ?? statsFixture);
      if (url.pathname === '/api/v1/content')
        return jsonResponse(overrides.recent ?? recentFixture);
      if (url.pathname === '/api/v1/weak-queries')
        return jsonResponse(overrides.weakQueries ?? weakQueriesFixture);
      return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
    },
  );
  global.fetch = fetchMock;
  return fetchMock;
}

function renderScreen() {
  return render(
    <Providers>
      <DashboardScreen />
    </Providers>,
  );
}

describe('DashboardScreen', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

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

    // Assert the visible surface (an alert region carries *some* text), not ErrorState's
    // internals/props — and never the raw API error body (FRONTEND-CONVENTIONS.md §9).
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
      // phase-9 task-19: this bypasses `mockFetch` (same reasoning as the new "shows the card
      // error" test below), so the weak-queries route needs its own success case here too — left
      // in the catch-all 500 below, it would render a SECOND `role="alert"` (the weak-queries
      // card's own `ErrorState`) and make this test's `findByRole('alert')` ambiguous. Unrelated
      // to what this test actually asserts (recent-content failure).
      if (url.pathname === '/api/v1/weak-queries') return jsonResponse(weakQueriesFixture);
      return jsonResponse({ error: { code: 'internal_error', message: 'boom' } }, 500);
    });

    renderScreen();

    expect(await screen.findByRole('link', { name: /^Draft\s*3$/ })).toBeInTheDocument();
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't load recent content.");
  });

  // phase-9 task-19 (RED): the dashboard has no weak-queries panel yet, and
  // `GET /api/v1/weak-queries` doesn't exist yet either — both new tests below fail against
  // today's `DashboardScreen` (no such title/table renders) until the implementer wires the
  // route + card.
  it('renders the weak-queries card from GET /api/v1/weak-queries', async () => {
    mockFetch();

    renderScreen();

    const table = await screen.findByRole('table', { name: 'Weak queries' });
    expect(screen.getByText('Weak queries (last 7 days)')).toBeInTheDocument();
    expect(within(table).getByText('does the firm cover crypto rsus')).toBeInTheDocument();
    expect(within(table).getByText('Thumbs down')).toBeInTheDocument();
  });

  it('shows the card error without blanking the dashboard', async () => {
    global.fetch = vi.fn<(input: RequestInfo | URL) => Promise<Response>>(async (input) => {
      const url = new URL(requestUrl(input));
      if (url.pathname === '/api/v1/stats') return jsonResponse(statsFixture);
      if (url.pathname === '/api/v1/content') return jsonResponse(recentFixture);
      return jsonResponse({ error: { code: 'internal_error', message: 'boom' } }, 500);
    });

    renderScreen();

    expect(await screen.findByRole('link', { name: /^Draft\s*3$/ })).toBeInTheDocument();
    expect(await screen.findByText("Couldn't load weak queries.")).toBeInTheDocument();
  });
});
