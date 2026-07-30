import { afterEach, describe, expect, it, vi } from 'vitest';

import { contentApi } from '@/lib/api/contentApi';
import { statsApi } from '@/lib/api/statsApi';
import { tagsApi } from '@/lib/api/tagsApi';
import { store } from '@/lib/store';
import type { ContentDto, ContentListDto } from '@/types/api/content';

// task-06 / PRD §5.2, §4 (slug immutable — never part of any request body here): the
// content-editor endpoints extending task-05's `contentApi` slice. `listContent` and
// `deleteContent` stay pinned, untouched, in contentApi.test.ts (this same folder) — this
// file ONLY covers the task-06 additions: `getContent`, `createContent`, `updateContent`,
// `publishContent`, `archiveContent`. None of these exist on `contentApi.endpoints` yet
// (task-06 Step 1) — `contentApi.endpoints.getContent` etc. are `undefined`, so every
// `.initiate(...)` call below throws a `TypeError` synchronously: correct RED until the
// implementer adds them to apps/admin/src/lib/api/contentApi.ts (task-06 Interfaces).
//
// Endpoint arg shapes pinned by this file (test-author decision — the brief's prose
// "updateContent(id, patch)" is not a literal RTK Query call signature, since `.initiate()`
// always takes exactly one argument):
//   getContent.initiate(id: string)
//   createContent.initiate({ title, body_md, tags })
//   updateContent.initiate({ id, patch })   — `patch` is the PATCH body verbatim (tri-state:
//                                              a key omitted from `patch` must not appear in
//                                              the request body at all)
//   publishContent.initiate(id: string)
//   archiveContent.initiate(id: string)
//
// Request-aware fetch mocking (task-04 review lesson, mirrored from contentApi.test.ts):
// `fetchBaseQuery` hands the mocked `fetch` a pre-built native `Request`, not a `(url, init)`
// pair — resolve the URL/method off the `Request` itself, and read its JSON body via
// `input.clone().json()` (per the task-06 brief) so the original `Request`'s body stream is
// never consumed out from under RTK Query's own retry/observability path.
function requestUrl(input: RequestInfo | URL): string {
  return input instanceof Request ? input.url : String(input);
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return input instanceof Request ? input.method : (init?.method ?? 'GET');
}

function pathnameOf(input: RequestInfo | URL): string {
  return new URL(requestUrl(input)).pathname;
}

async function requestJson(input: RequestInfo | URL): Promise<unknown> {
  if (input instanceof Request) {
    return input.clone().json();
  }
  return undefined;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const contentFixtureA: ContentDto = {
  author_id: null,
  body_md:
    '# Roth IRA Conversion Basics\n\nSample content for demonstration purposes — not financial advice.',
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

const listFixture: ContentListDto = {
  items: [contentFixtureA],
  page: 1,
  page_size: 20,
  total: 1,
};

const statsFixture = {
  by_status: { draft: 3, published: 5, archived: 1 },
  by_tag: { 'tax-planning': 2, retirement: 1 },
};

const tagsFixture = [
  { id: 'aaaaaaaa-1111-1111-1111-111111111111', name: 'tax-planning', count: 2 },
];

// Every route this file's endpoints can hit.
function mockFetch() {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
    async (input, init) => {
      const pathname = pathnameOf(input);
      const method = requestMethod(input, init);

      if (pathname === '/api/v1/content' && method === 'GET') {
        return jsonResponse(listFixture);
      }
      if (pathname === '/api/v1/content' && method === 'POST') {
        return jsonResponse(
          { ...contentFixtureA, id: '99999999-9999-9999-9999-999999999999' },
          201,
        );
      }
      if (pathname === `/api/v1/content/${contentFixtureA.id}/publish` && method === 'POST') {
        return jsonResponse({
          ...contentFixtureA,
          status: 'published',
          published_at: '2026-02-01T00:00:00Z',
        });
      }
      if (pathname === `/api/v1/content/${contentFixtureA.id}/archive` && method === 'POST') {
        return jsonResponse({ ...contentFixtureA, status: 'archived' });
      }
      if (pathname === `/api/v1/content/${contentFixtureA.id}` && method === 'GET') {
        return jsonResponse(contentFixtureA);
      }
      if (pathname === `/api/v1/content/${contentFixtureA.id}` && method === 'PATCH') {
        return jsonResponse({ ...contentFixtureA, title: 'Updated Title' });
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

describe('contentApi editor endpoints', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('getContent issues GET /api/v1/content/{id}', async () => {
    const fetchMock = mockFetch();

    await store.dispatch(contentApi.endpoints.getContent.initiate(contentFixtureA.id));

    const call = fetchMock.mock.calls.find(
      ([input, init]) =>
        pathnameOf(input) === `/api/v1/content/${contentFixtureA.id}` &&
        requestMethod(input, init) === 'GET',
    );
    expect(call).toBeDefined();
  });

  it('createContent issues POST /api/v1/content with exactly {title, body_md, tags}', async () => {
    const fetchMock = mockFetch();

    await store.dispatch(
      contentApi.endpoints.createContent.initiate({
        title: 'New Piece',
        body_md: '# New body',
        tags: ['retirement'],
      }),
    );

    const call = fetchMock.mock.calls.find(
      ([input, init]) =>
        pathnameOf(input) === '/api/v1/content' && requestMethod(input, init) === 'POST',
    );
    expect(call).toBeDefined();
    const body = await requestJson(call![0]);
    expect(body).toEqual({ title: 'New Piece', body_md: '# New body', tags: ['retirement'] });
  });

  it('updateContent({id, patch:{title}}) PATCHes /api/v1/content/{id} with ONLY the given field — the tri-state: omitted keys never appear in the body', async () => {
    const fetchMock = mockFetch();

    await store.dispatch(
      contentApi.endpoints.updateContent.initiate({
        id: contentFixtureA.id,
        patch: { title: 'Updated Title' },
      }),
    );

    const call = fetchMock.mock.calls.find(
      ([input, init]) =>
        pathnameOf(input) === `/api/v1/content/${contentFixtureA.id}` &&
        requestMethod(input, init) === 'PATCH',
    );
    expect(call).toBeDefined();
    const body = (await requestJson(call![0])) as Record<string, unknown>;
    expect(body).toEqual({ title: 'Updated Title' });
    expect(Object.keys(body)).not.toContain('body_md');
    expect(Object.keys(body)).not.toContain('tags');
  });

  it('publishContent(id) issues POST /api/v1/content/{id}/publish', async () => {
    const fetchMock = mockFetch();

    await store.dispatch(contentApi.endpoints.publishContent.initiate(contentFixtureA.id));

    const call = fetchMock.mock.calls.find(
      ([input, init]) =>
        pathnameOf(input) === `/api/v1/content/${contentFixtureA.id}/publish` &&
        requestMethod(input, init) === 'POST',
    );
    expect(call).toBeDefined();
  });

  it('archiveContent(id) issues POST /api/v1/content/{id}/archive', async () => {
    const fetchMock = mockFetch();

    await store.dispatch(contentApi.endpoints.archiveContent.initiate(contentFixtureA.id));

    const call = fetchMock.mock.calls.find(
      ([input, init]) =>
        pathnameOf(input) === `/api/v1/content/${contentFixtureA.id}/archive` &&
        requestMethod(input, init) === 'POST',
    );
    expect(call).toBeDefined();
  });

  it('createContent invalidates Content + Stats + Tags — subscribed queries for all three refetch with no manual refetch call', async () => {
    const fetchMock = mockFetch();

    // Simulate the content-list, dashboard, and tag-filter screens all being mounted
    // (subscribed) when the create happens.
    const listSubscription = store.dispatch(contentApi.endpoints.listContent.initiate({}));
    const statsSubscription = store.dispatch(statsApi.endpoints.getStats.initiate());
    const tagsSubscription = store.dispatch(tagsApi.endpoints.listTags.initiate());
    await listSubscription;
    await statsSubscription;
    await tagsSubscription;

    // Only calls made from this point on are attributable to the create + its invalidation.
    fetchMock.mockClear();

    await store.dispatch(
      contentApi.endpoints.createContent.initiate({
        title: 'New Piece',
        body_md: '# New body',
        tags: ['retirement'],
      }),
    );

    const getCallsTo = (pathname: string) =>
      fetchMock.mock.calls.filter(
        ([input, init]) => pathnameOf(input) === pathname && requestMethod(input, init) === 'GET',
      );

    // No `.refetch()` / re-`initiate()` was called above for any of these three — RTK
    // Query's tag-invalidation middleware must be what re-issues them.
    expect(getCallsTo('/api/v1/content').length).toBeGreaterThanOrEqual(1);
    expect(getCallsTo('/api/v1/stats').length).toBeGreaterThanOrEqual(1);
    expect(getCallsTo('/api/v1/tags').length).toBeGreaterThanOrEqual(1);

    listSubscription.unsubscribe();
    statsSubscription.unsubscribe();
    tagsSubscription.unsubscribe();
  });

  it('updateContent invalidates Content — a subscribed list query refetches with no manual refetch call', async () => {
    const fetchMock = mockFetch();

    const listSubscription = store.dispatch(contentApi.endpoints.listContent.initiate({}));
    await listSubscription;
    fetchMock.mockClear();

    await store.dispatch(
      contentApi.endpoints.updateContent.initiate({
        id: contentFixtureA.id,
        patch: { title: 'Updated Title' },
      }),
    );

    const listCalls = fetchMock.mock.calls.filter(
      ([input, init]) =>
        pathnameOf(input) === '/api/v1/content' && requestMethod(input, init) === 'GET',
    );
    expect(listCalls.length).toBeGreaterThanOrEqual(1);

    listSubscription.unsubscribe();
  });

  it('publishContent invalidates Content — a subscribed list query refetches with no manual refetch call', async () => {
    const fetchMock = mockFetch();

    const listSubscription = store.dispatch(contentApi.endpoints.listContent.initiate({}));
    await listSubscription;
    fetchMock.mockClear();

    await store.dispatch(contentApi.endpoints.publishContent.initiate(contentFixtureA.id));

    const listCalls = fetchMock.mock.calls.filter(
      ([input, init]) =>
        pathnameOf(input) === '/api/v1/content' && requestMethod(input, init) === 'GET',
    );
    expect(listCalls.length).toBeGreaterThanOrEqual(1);

    listSubscription.unsubscribe();
  });

  it('archiveContent invalidates Content — a subscribed list query refetches with no manual refetch call', async () => {
    const fetchMock = mockFetch();

    const listSubscription = store.dispatch(contentApi.endpoints.listContent.initiate({}));
    await listSubscription;
    fetchMock.mockClear();

    await store.dispatch(contentApi.endpoints.archiveContent.initiate(contentFixtureA.id));

    const listCalls = fetchMock.mock.calls.filter(
      ([input, init]) =>
        pathnameOf(input) === '/api/v1/content' && requestMethod(input, init) === 'GET',
    );
    expect(listCalls.length).toBeGreaterThanOrEqual(1);

    listSubscription.unsubscribe();
  });
});
