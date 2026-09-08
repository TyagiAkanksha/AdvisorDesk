// @vitest-environment jsdom
import { render, screen, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import type { ConnectedAppDto, ConnectedAppsResponseDto } from '@/types/api/connectedApps';

import { ConnectedAppsScreen } from '.';

// docs/plans/mcp-oauth/task-09-admin-connected-apps-ui.md: the admin "Connected apps" page lists
// every OAuth client from `GET /api/v1/oauth/clients` (task-08's admin-management endpoint) —
// name, consent date, live tokens, last used, expiry. Mock ONLY the network edge
// (docs/FRONTEND-CONVENTIONS.md §7); ConnectedAppsScreen, connectedAppsApi, baseApi, the store,
// and Providers are all real, unmocked modules.
//
// Request-aware fetch mocking (task-04 review lesson, mirrored from DashboardScreen's
// Component.test.tsx in this same app): `fetchBaseQuery` hands the mocked `fetch` a native
// `Request`, which stringifies to `"[object Request]"` — resolve the real URL off the `Request`
// itself, not `String(input)`.
function requestUrl(input: RequestInfo | URL): string {
  return input instanceof Request ? input.url : String(input);
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

// Task-09 brief facts: `client_id: 'adkc_abc'` on the first fixture app is load-bearing —
// revoke.test.tsx's DELETE URL assertion depends on it. `active_access_tokens` /
// `active_refresh_tokens` are deliberately different numbers (2 vs 1) so the two counts render
// as distinct text nodes within the row — same value for both would make `within(row).getByText`
// ambiguous.
const appA: ConnectedAppDto = {
  active_access_tokens: 2,
  active_refresh_tokens: 1,
  client_id: 'adkc_abc',
  client_name: 'Claude',
  consent_granted_at: '2026-01-01T00:05:00Z',
  created_at: '2026-01-01T00:00:00Z',
  last_used_at: '2026-02-01T00:00:00Z',
  latest_expires_at: '2026-02-01T01:00:00Z',
  redirect_uris: ['https://claude.ai/api/mcp/auth_callback'],
};

// Second fixture app per brief facts: `client_id: 'adkc_def'`, `client_name: 'Other MCP client'`,
// `last_used_at: null` (exercises the `—` placeholder for a null date). `latest_expires_at` is
// also `null` here — consistent with zero active tokens (nothing to expire).
const appB: ConnectedAppDto = {
  active_access_tokens: 0,
  active_refresh_tokens: 0,
  client_id: 'adkc_def',
  client_name: 'Other MCP client',
  consent_granted_at: '2026-01-02T00:05:00Z',
  created_at: '2026-01-02T00:00:00Z',
  last_used_at: null,
  latest_expires_at: null,
  redirect_uris: ['https://example.com/callback'],
};

const listFixture: ConnectedAppsResponseDto = { items: [appA, appB] };

function renderScreen() {
  return render(
    <Providers>
      <ConnectedAppsScreen />
    </Providers>,
  );
}

describe('ConnectedAppsScreen', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders one row per connected app with name, counts, and formatted dates', async () => {
    global.fetch = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async () => jsonResponse(listFixture),
    );

    renderScreen();

    // Table columns (header text exact, brief's Screen behaviour section).
    expect(await screen.findByText('App')).toBeInTheDocument();
    expect(screen.getByText('Approved')).toBeInTheDocument();
    expect(screen.getByText('Access tokens')).toBeInTheDocument();
    expect(screen.getByText('Refresh tokens')).toBeInTheDocument();
    expect(screen.getByText('Last used')).toBeInTheDocument();
    expect(screen.getByText('Expires')).toBeInTheDocument();

    const rowA = screen.getByTestId('connected-app-adkc_abc');
    expect(within(rowA).getByText('Claude')).toBeInTheDocument();
    expect(within(rowA).getByText(String(appA.active_access_tokens))).toBeInTheDocument();
    expect(within(rowA).getByText(String(appA.active_refresh_tokens))).toBeInTheDocument();
    expect(
      within(rowA).getByText(new Date(appA.consent_granted_at as string).toLocaleString()),
    ).toBeInTheDocument();
    expect(
      within(rowA).getByText(new Date(appA.last_used_at as string).toLocaleString()),
    ).toBeInTheDocument();
    expect(
      within(rowA).getByText(new Date(appA.latest_expires_at as string).toLocaleString()),
    ).toBeInTheDocument();
    expect(within(rowA).getByRole('button', { name: 'Revoke Claude' })).toBeInTheDocument();

    const rowB = screen.getByTestId('connected-app-adkc_def');
    expect(within(rowB).getByText('Other MCP client')).toBeInTheDocument();
    // Both `last_used_at: null` and `latest_expires_at: null` render as the placeholder dash
    // (brief's Screen behaviour section) — two distinct cells in this row.
    expect(within(rowB).getAllByText('—')).toHaveLength(2);
    expect(
      within(rowB).getByRole('button', { name: 'Revoke Other MCP client' }),
    ).toBeInTheDocument();
  });

  it('renders EmptyState when the list is empty', async () => {
    global.fetch = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async () => jsonResponse({ items: [] }),
    );

    renderScreen();

    expect(await screen.findByText('No connected apps')).toBeInTheDocument();
    expect(
      screen.getByText(
        'Apps that connect over MCP (like Claude) will appear here after you approve them.',
      ),
    ).toBeInTheDocument();
  });

  it('renders LoadingIndicator while the first load is pending', () => {
    // A fetch that never resolves keeps `getConnectedApps` in its loading state for the test's
    // life (mirrors DashboardScreen's Component.test.tsx pattern).
    global.fetch = vi.fn(() => new Promise<Response>(() => {}));

    renderScreen();

    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  it('renders ErrorState with the envelope message on a 500 first load', async () => {
    global.fetch = vi.fn(async () =>
      jsonResponse({ error: { code: 'internal', message: 'boom' } }, 500),
    );

    renderScreen();

    // Assert the visible surface (an alert region carries the message), not ErrorState's
    // internals/props — and never a raw error body (FRONTEND-CONVENTIONS.md §9).
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('boom');
  });

  it('GET hits /api/v1/oauth/clients with credentials', async () => {
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async () => jsonResponse(listFixture),
    );
    global.fetch = fetchMock;

    renderScreen();

    await screen.findByTestId('connected-app-adkc_abc');

    // `fetchMock.mock.calls[0]` is `[...] | undefined` under `noUncheckedIndexedAccess`; assert
    // it was actually called first (mirrors AppShell's Component.test.tsx `!`-after-toBeDefined
    // idiom for the same shape of access).
    expect(fetchMock.mock.calls.length).toBeGreaterThan(0);
    const [request] = fetchMock.mock.calls[0]!;
    expect(requestUrl(request)).toMatch(/\/api\/v1\/oauth\/clients$/);
    expect(request).toBeInstanceOf(Request);
    expect((request as Request).credentials).toBe('include');
  });
});
