// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import { contentApi } from '@/lib/api/contentApi';
import { store } from '@/lib/store';
import type { ContentDto, ContentListDto } from '@/types/api/content';

import { ContentListScreen } from '.';

// Final review, finding F8/C-4 (propagates task-06 fix round 1 F3's resilience pattern to the
// content list): a background refetch (e.g. another screen's mutation invalidating the
// `'Content'` tag while this list is still mounted) failing must not blank the whole list back
// to `ErrorState` — the last successfully loaded page stays visible (table + pager), with the
// failure surfaced as a banner instead.
//
// Mocking conventions mirror the pinned Component.test.tsx in this same folder exactly
// (docs/FRONTEND-CONVENTIONS.md §7 — mock only the network edge); the SECOND fetch is forced by
// dispatching a real tag invalidation against the shared store (`vitest.setup.ts`: the store is
// a real singleton every component test renders around, reset in `afterEach`) — exactly the
// mechanism a real cross-screen mutation would trigger, not a simulated prop/state change.
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

const listFixture: ContentListDto = {
  items: [itemA],
  page: 1,
  page_size: 20,
  total: 1,
};

function renderScreen() {
  return render(
    <Providers>
      <ContentListScreen />
    </Providers>,
  );
}

describe('ContentListScreen resilient background refetch', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('a failed background refetch keeps the last loaded page (table + pager) visible and surfaces an alert', async () => {
    let listGetCalls = 0;
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async (input, init) => {
        const pathname = pathnameOf(input);
        const method = requestMethod(input, init);

        if (pathname === '/api/v1/content' && method === 'GET') {
          listGetCalls += 1;
          // First GET (initial mount) succeeds; every GET after that (the forced
          // invalidation-driven refetch below) fails.
          if (listGetCalls === 1) {
            return jsonResponse(listFixture);
          }
          return jsonResponse(
            { error: { code: 'internal_error', message: 'Refresh failed.' } },
            500,
          );
        }
        if (pathname === '/api/v1/tags' && method === 'GET') {
          return jsonResponse([]);
        }
        return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
      },
    );
    global.fetch = fetchMock;

    renderScreen();

    const row = await screen.findByRole('row', { name: new RegExp(itemA.title) });
    expect(row).toBeInTheDocument();

    // Simulate a cross-screen mutation invalidating the `'Content'` tag while this screen is
    // still mounted — RTK Query issues a real refetch for the still-subscribed `listContent`
    // query.
    store.dispatch(contentApi.util.invalidateTags(['Content']));

    await waitFor(() => expect(listGetCalls).toBeGreaterThanOrEqual(2));

    // Non-destructive: the last successfully loaded row and the pager are both still on
    // screen — never replaced by `ErrorState`.
    expect(screen.getByRole('row', { name: new RegExp(itemA.title) })).toBeInTheDocument();
    expect(screen.queryByText("Couldn't load content.")).not.toBeInTheDocument();

    const alert = await screen.findByRole('alert');
    expect(alert).toBeVisible();
    expect(alert.textContent?.trim().length).toBeGreaterThan(0);
  });
});
