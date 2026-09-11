// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import { statsApi } from '@/lib/api/statsApi';
import { store } from '@/lib/store';
import type { ContentListDto } from '@/types/api/content';

import { DashboardScreen } from '.';

// Final review, finding F8/C-4 (propagates task-06 fix round 1 F3's resilience pattern to the
// dashboard): a background refetch (e.g. another screen's mutation invalidating the `'Stats'`
// tag while the dashboard is still mounted) failing must not blank the whole dashboard back to
// `ErrorState` — the last successfully loaded counts stay visible, with the failure surfaced as
// a banner instead.
//
// Mocking conventions mirror the pinned Component.test.tsx in this same folder exactly
// (docs/FRONTEND-CONVENTIONS.md §7 — mock only the network edge); the SECOND fetch is forced
// by dispatching a real tag invalidation against the shared store (`vitest.setup.ts`: the store
// is a real singleton every component test renders around, reset in `afterEach`) — exactly the
// mechanism a real cross-screen mutation would trigger, not a simulated prop/state change.
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

// task-17: the dashboard now also issues `GET /api/v1/content` (recent content). This mock's
// assertions are unchanged — the route is added only so that query no longer 404s while this
// screen exercises the background-refetch-resilience path on `GET /stats`.
const recentFixture: ContentListDto = {
  items: [
    {
      author_id: null,
      body_md: '# Recent Item',
      created_at: '2026-01-01T12:00:00Z',
      id: '33333333-3333-3333-3333-333333333333',
      published_at: null,
      slug: 'recent-item',
      status: 'draft',
      tags: [],
      title: 'Recent Item',
      updated_at: '2026-01-02T12:00:00Z',
      updated_by: null,
    },
  ],
  page: 1,
  page_size: 5,
  total: 1,
};

function renderScreen() {
  return render(
    <Providers>
      <DashboardScreen />
    </Providers>,
  );
}

describe('DashboardScreen resilient background refetch', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('a failed background refetch keeps the last loaded stats visible and surfaces an alert', async () => {
    let getCalls = 0;
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async (input) => {
        if (requestUrl(input).includes('/stats')) {
          getCalls += 1;
          // First GET (initial mount) succeeds; every GET after that (the forced
          // invalidation-driven refetch below) fails.
          if (getCalls === 1) {
            return jsonResponse(statsFixture);
          }
          return jsonResponse(
            { error: { code: 'internal_error', message: 'Refresh failed.' } },
            500,
          );
        }
        if (requestUrl(input).includes('/api/v1/content')) {
          return jsonResponse(recentFixture);
        }
        return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
      },
    );
    global.fetch = fetchMock;

    renderScreen();

    expect(await screen.findByText('3')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();

    // Simulate a cross-screen mutation invalidating the `'Stats'` tag while this screen is
    // still mounted — RTK Query issues a real refetch for the still-subscribed `getStats` query.
    store.dispatch(statsApi.util.invalidateTags(['Stats']));

    await waitFor(() => expect(getCalls).toBeGreaterThanOrEqual(2));

    // Non-destructive: the last successfully loaded counts are still on screen — never
    // replaced by `ErrorState`.
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.queryByText("Couldn't load the dashboard stats.")).not.toBeInTheDocument();

    const alert = await screen.findByRole('alert');
    expect(alert).toBeVisible();
    expect(alert.textContent?.trim().length).toBeGreaterThan(0);
  });
});
