// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import type { ContentListDto } from '@/types/api/content';

import { ContentListScreen } from '.';

// fix round 1, F1 (Critical): /content/new was unreachable — nothing in the admin UI linked to
// it. `ContentListScreen`'s header now renders a "New content" link (common/Button with `href`,
// which MUI renders as a real `<a>` — no JS-driven navigation, same pattern already used by
// `SignInScreen`'s login Button).
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

const emptyFixture: ContentListDto = { items: [], page: 1, page_size: 20, total: 0 };

function mockFetch() {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
    async (input, init) => {
      const pathname = pathnameOf(input);
      const method = requestMethod(input, init);

      if (pathname === '/api/v1/content' && method === 'GET') {
        return jsonResponse(emptyFixture);
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

describe('ContentListScreen new-content entry point', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders a "New content" link to /content/new', async () => {
    mockFetch();

    renderScreen();

    const link = await screen.findByRole('link', { name: /new content/i });
    expect(link).toHaveAttribute('href', '/content/new');
  });
});
