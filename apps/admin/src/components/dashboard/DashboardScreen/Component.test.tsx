// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';

import { DashboardScreen } from '.';

// task-05 / PRD §2.2: the dashboard renders one card per content status with the count from
// `GET /stats`. Mock ONLY the network edge (docs/FRONTEND-CONVENTIONS.md §7); DashboardScreen,
// statsApi, baseApi, the store, and Providers are all real, unmocked modules.
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

  it('renders one card per content status with the count from GET /stats', async () => {
    global.fetch = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async (input) => {
        if (requestUrl(input).includes('/stats')) return jsonResponse(statsFixture);
        return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
      },
    );

    renderScreen();

    // One heading per known status (role/heading, per instructions), each paired with its
    // count from the fixture (by role/text).
    expect(await screen.findByRole('heading', { name: /draft/i })).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();

    expect(screen.getByRole('heading', { name: /published/i })).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();

    expect(screen.getByRole('heading', { name: /archived/i })).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('shows a visible loading indicator (not a silent blank) while GET /stats is pending', () => {
    // A fetch that never resolves keeps `getStats` in its loading state for the test's life.
    global.fetch = vi.fn(() => new Promise<Response>(() => {}));

    renderScreen();

    expect(screen.getByRole('progressbar')).toBeInTheDocument();
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
});
