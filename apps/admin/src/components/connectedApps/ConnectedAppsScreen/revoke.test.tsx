// @vitest-environment jsdom
import { render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import type { ConnectedAppDto, ConnectedAppsResponseDto } from '@/types/api/connectedApps';

import { ConnectedAppsScreen } from '.';

// docs/plans/mcp-oauth/task-09-admin-connected-apps-ui.md: Revoke goes through `ConfirmDialog`
// (`DELETE /api/v1/oauth/clients/{client_id}`) and refetches the list on success, staying open
// with the §9 envelope message on failure. Mock ONLY the network edge
// (docs/FRONTEND-CONVENTIONS.md §7) — mirrors ContentListScreen's deleteError.test.tsx in this
// same app exactly (a mocked `fetch` returning different responses per call, keyed on
// pathname/method).
//
// Request-aware fetch mocking (task-04 review lesson): `fetchBaseQuery` hands the mocked `fetch`
// a native `Request`, which stringifies to `"[object Request]"` — resolve the real URL/method off
// the `Request` itself, not `String(input)`/a plain `init`.
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

// `client_id: 'adkc_abc'` is load-bearing — the DELETE URL assertions below depend on it
// (task-09 brief facts).
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

const twoAppsFixture: ConnectedAppsResponseDto = { items: [appA, appB] };
const oneAppFixture: ConnectedAppsResponseDto = { items: [appB] };

function renderScreen() {
  return render(
    <Providers>
      <ConnectedAppsScreen />
    </Providers>,
  );
}

describe('ConnectedAppsScreen revoke', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('clicking Revoke opens the confirm dialog naming the app', async () => {
    global.fetch = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async () => jsonResponse(twoAppsFixture),
    );
    const user = userEvent.setup();

    renderScreen();

    await screen.findByTestId('connected-app-adkc_abc');
    await user.click(screen.getByRole('button', { name: 'Revoke Claude' }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Revoke access?')).toBeInTheDocument();
    expect(dialog).toHaveTextContent('Claude');
  });

  it('confirming sends DELETE and the row disappears after refetch', async () => {
    let getCalls = 0;
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async (input, init) => {
        const pathname = pathnameOf(input);
        const method = requestMethod(input, init);

        if (pathname === '/api/v1/oauth/clients' && method === 'GET') {
          getCalls += 1;
          // First GET (initial mount) returns both apps; the second GET (the refetch RTK
          // Query issues once `ConnectedApps` is invalidated by a successful revoke) returns
          // only the one that's left.
          return getCalls === 1 ? jsonResponse(twoAppsFixture) : jsonResponse(oneAppFixture);
        }
        if (pathname === '/api/v1/oauth/clients/adkc_abc' && method === 'DELETE') {
          return new Response(null, { status: 204 });
        }
        return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
      },
    );
    global.fetch = fetchMock;
    const user = userEvent.setup();

    renderScreen();

    await screen.findByTestId('connected-app-adkc_abc');
    await user.click(screen.getByRole('button', { name: 'Revoke Claude' }));

    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Revoke' }));

    await waitFor(() => {
      const deleteCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          pathnameOf(input) === '/api/v1/oauth/clients/adkc_abc' &&
          requestMethod(input, init) === 'DELETE',
      );
      expect(deleteCall).toBeDefined();
    });

    await waitFor(() =>
      expect(screen.queryByTestId('connected-app-adkc_abc')).not.toBeInTheDocument(),
    );
    expect(screen.getByTestId('connected-app-adkc_def')).toBeInTheDocument();
  });

  it('a failed DELETE keeps the dialog open and shows the envelope message', async () => {
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async (input, init) => {
        const pathname = pathnameOf(input);
        const method = requestMethod(input, init);

        if (pathname === '/api/v1/oauth/clients' && method === 'GET') {
          return jsonResponse(twoAppsFixture);
        }
        if (pathname === '/api/v1/oauth/clients/adkc_abc' && method === 'DELETE') {
          return jsonResponse({ error: { code: 'internal', message: 'nope' } }, 500);
        }
        return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
      },
    );
    global.fetch = fetchMock;
    const user = userEvent.setup();

    renderScreen();

    await screen.findByTestId('connected-app-adkc_abc');
    await user.click(screen.getByRole('button', { name: 'Revoke Claude' }));

    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Revoke' }));

    // The envelope's message is visible inside the still-open dialog as an alert (never a raw
    // error body — docs/FRONTEND-CONVENTIONS.md §9); both rows remain (nothing was revoked).
    const alert = await within(dialog).findByRole('alert');
    expect(alert).toHaveTextContent('nope');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByTestId('connected-app-adkc_abc')).toBeInTheDocument();
    expect(screen.getByTestId('connected-app-adkc_def')).toBeInTheDocument();
  });

  it('cancel closes the dialog without a request', async () => {
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async (input, init) => {
        const pathname = pathnameOf(input);
        const method = requestMethod(input, init);

        if (pathname === '/api/v1/oauth/clients' && method === 'GET') {
          return jsonResponse(twoAppsFixture);
        }
        return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
      },
    );
    global.fetch = fetchMock;
    const user = userEvent.setup();

    renderScreen();

    await screen.findByTestId('connected-app-adkc_abc');
    await user.click(screen.getByRole('button', { name: 'Revoke Claude' }));

    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

    const deleteCall = fetchMock.mock.calls.find(
      ([input, init]) =>
        pathnameOf(input) === '/api/v1/oauth/clients/adkc_abc' &&
        requestMethod(input, init) === 'DELETE',
    );
    expect(deleteCall).toBeUndefined();
  });
});
