import { afterEach, describe, expect, it, vi } from 'vitest';

import { contentApi } from '@/lib/api/contentApi';
import { statsApi } from '@/lib/api/statsApi';
import { tagsApi } from '@/lib/api/tagsApi';
import { store } from '@/lib/store';
import type { ContentDto, ContentListDto } from '@/types/api/content';

// task-05 / PRD §5.2: `contentApi` is the per-domain RTK Query slice the dashboard and
// content-list screens read from. Pin here, against the real `store` + `baseApi` (only
// `global.fetch` is mocked — docs/FRONTEND-CONVENTIONS.md §7):
//   1. `listContent` serializes exactly the given query params (and omits the rest —
//      no empty-string params for filters the caller didn't set).
//   2. `deleteContent` issues `DELETE /api/v1/content/{id}`.
//   3. `deleteContent` invalidates `['Content','Stats','Tags']` (task-05 Interfaces) so every
//      *subscribed* query for those tags refetches on its own — no manual `.refetch()` call
//      anywhere in this file proves that.
//
// Request-aware fetch mocking (task-04 review lesson): `fetchBaseQuery` hands the mocked
// `fetch` a pre-built native `Request`, not a `(url, init)` pair — `Request` stringifies to
// `"[object Request]"`, so resolve the URL/method from the `Request` itself when that's the
// calling convention, else fall back to `init`.
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

const contentFixtureA: ContentDto = {
  author_id: null,
  body_md: '# Roth IRA Conversion Basics\n\nSample content for demonstration purposes — not financial advice.',
  created_at: '2026-01-01T00:00:00Z',
  id: '11111111-1111-1111-1111-111111111111',
  published_at: null,
  slug: 'roth-ira-conversion-basics',
  status: 'draft',
  tags: ['tax-planning'],
  title: 'Roth IRA Conversion Basics',
  updated_at: '2026-01-02T00:00:00Z',
  updated_by: null,
};

const contentFixtureB: ContentDto = {
  author_id: null,
  body_md: '# Estate Planning 101\n\nSample content for demonstration purposes — not financial advice.',
  created_at: '2025-12-01T00:00:00Z',
  id: '22222222-2222-2222-2222-222222222222',
  published_at: '2025-12-05T00:00:00Z',
  slug: 'estate-planning-101',
  status: 'published',
  tags: ['estate-planning', 'retirement'],
  title: 'Estate Planning 101',
  updated_at: '2025-12-06T00:00:00Z',
  updated_by: null,
};

const listFixture: ContentListDto = {
  items: [contentFixtureA, contentFixtureB],
  page: 1,
  page_size: 20,
  total: 2,
};

const statsFixture = {
  by_status: { draft: 3, published: 5, archived: 1 },
  by_tag: { 'tax-planning': 2, retirement: 1 },
};

const tagsFixture = [
  { id: 'aaaaaaaa-1111-1111-1111-111111111111', name: 'tax-planning', count: 2 },
  { id: 'bbbbbbbb-2222-2222-2222-222222222222', name: 'retirement', count: 1 },
];

// Every route this file's endpoints can hit. `deleteContent`'s response has no body
// (`DELETE /content/{id}` -> 204, apps/api/openapi.json) — a bodyless `Response` is
// correct here, not a JSON stub.
function mockFetch() {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
    async (input, init) => {
      const pathname = pathnameOf(input);
      const method = requestMethod(input, init);

      if (pathname === '/api/v1/content' && method === 'GET') {
        return jsonResponse(listFixture);
      }
      if (pathname.startsWith('/api/v1/content/') && method === 'DELETE') {
        return new Response(null, { status: 204 });
      }
      if (pathname === '/api/v1/stats' && method === 'GET') {
        return jsonResponse(statsFixture);
      }
      if (pathname === '/api/v1/tags' && method === 'GET') {
        return jsonResponse(tagsFixture);
      }
      return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
    },
  );
  global.fetch = fetchMock;
  return fetchMock;
}

describe('contentApi', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('listContent issues GET /api/v1/content with exactly the given query params', async () => {
    const fetchMock = mockFetch();

    await store.dispatch(
      contentApi.endpoints.listContent.initiate({
        status: 'draft',
        tag: 'tax-planning',
        q: 'roth',
        page: 2,
        page_size: 10,
      }),
    );

    const listCall = fetchMock.mock.calls.find(
      ([input, init]) => pathnameOf(input) === '/api/v1/content' && requestMethod(input, init) === 'GET',
    );
    expect(listCall).toBeDefined();
    const url = new URL(requestUrl(listCall![0]));

    expect(url.searchParams.get('status')).toBe('draft');
    expect(url.searchParams.get('tag')).toBe('tax-planning');
    expect(url.searchParams.get('q')).toBe('roth');
    expect(url.searchParams.get('page')).toBe('2');
    expect(url.searchParams.get('page_size')).toBe('10');
    // "Exactly" — no extra params beyond the five given.
    expect(Array.from(url.searchParams.keys()).sort()).toEqual(
      ['page', 'page_size', 'q', 'status', 'tag'].sort(),
    );
  });

  it('listContent omits params the caller did not supply — no empty-string params on the URL', async () => {
    const fetchMock = mockFetch();

    await store.dispatch(contentApi.endpoints.listContent.initiate({ status: 'published' }));

    const listCall = fetchMock.mock.calls.find(
      ([input, init]) => pathnameOf(input) === '/api/v1/content' && requestMethod(input, init) === 'GET',
    );
    expect(listCall).toBeDefined();
    const url = new URL(requestUrl(listCall![0]));

    expect(url.searchParams.get('status')).toBe('published');
    expect(url.searchParams.has('tag')).toBe(false);
    expect(url.searchParams.has('q')).toBe(false);
    expect(url.searchParams.has('page')).toBe(false);
    expect(url.searchParams.has('page_size')).toBe(false);
  });

  it('deleteContent issues DELETE /api/v1/content/{id}', async () => {
    const fetchMock = mockFetch();
    const targetId = contentFixtureA.id;

    await store.dispatch(contentApi.endpoints.deleteContent.initiate(targetId));

    const deleteCall = fetchMock.mock.calls.find(
      ([input, init]) => requestMethod(input, init) === 'DELETE',
    );
    expect(deleteCall).toBeDefined();
    expect(pathnameOf(deleteCall![0])).toBe(`/api/v1/content/${targetId}`);
  });

  it('deleting content invalidates Content + Stats (+ Tags) so subscribed queries refetch with no manual refetch call', async () => {
    const fetchMock = mockFetch();

    // Simulate the dashboard + content-list screens both being mounted (subscribed) when
    // the delete happens — the exact scenario tag invalidation exists for.
    const listSubscription = store.dispatch(contentApi.endpoints.listContent.initiate({}));
    const statsSubscription = store.dispatch(statsApi.endpoints.getStats.initiate());
    const tagsSubscription = store.dispatch(tagsApi.endpoints.listTags.initiate());
    await listSubscription;
    await statsSubscription;
    await tagsSubscription;

    // Only calls made from this point on are attributable to the delete + its invalidation.
    fetchMock.mockClear();

    await store.dispatch(contentApi.endpoints.deleteContent.initiate(contentFixtureA.id));

    const getCallsTo = (pathname: string) =>
      fetchMock.mock.calls.filter(
        ([input, init]) => pathnameOf(input) === pathname && requestMethod(input, init) === 'GET',
      );

    // No `.refetch()` / re-`initiate()` was called above for any of these three — RTK Query's
    // tag-invalidation middleware must be what re-issues them.
    expect(getCallsTo('/api/v1/content').length).toBeGreaterThanOrEqual(1);
    expect(getCallsTo('/api/v1/stats').length).toBeGreaterThanOrEqual(1);
    expect(getCallsTo('/api/v1/tags').length).toBeGreaterThanOrEqual(1);

    listSubscription.unsubscribe();
    statsSubscription.unsubscribe();
    tagsSubscription.unsubscribe();
  });
});
