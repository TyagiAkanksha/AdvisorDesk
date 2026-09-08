// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';

import { AppShell } from '.';

// task-04: AppShell is the authenticated frame (AppBar + nav + user menu)
// tasks 05/06 and the phase-5 panel mount into. Mock ONLY the network edge
// (fetch) and the next/navigation framework seam (docs/FRONTEND-CONVENTIONS.md
// §7); AppShell, baseApi, authApi, the store, and Providers are all real.
const replaceMock = vi.fn();
const pushMock = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: replaceMock, push: pushMock }),
}));

// Contract pinned by this file: the account-menu trigger is a `button` whose
// accessible name contains the signed-in user's name (from `getMe`); clicking
// it opens a menu containing a `menuitem` named "Sign out".
const meFixture = {
  id: '11111111-1111-1111-1111-111111111111',
  email: 'ada@advisordesk.test',
  name: 'Ada Lovelace',
  avatar_url: null,
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

// Request-aware: `fetchBaseQuery` may hand the mocked `fetch` either a plain
// `(url, init)` pair or a single pre-built `Request` — and a `Request`
// stringifies to `"[object Request]"`, not its URL, so `String(input)`
// matching breaks for that calling convention. Resolve the real URL either
// way so mock matching is stable regardless of which shape is used.
function requestUrl(input: RequestInfo | URL): string {
  return input instanceof Request ? input.url : String(input);
}

function mockFetch() {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
    async (input) => {
      const url = requestUrl(input);
      if (url.includes('/auth/me')) return jsonResponse(meFixture, 200);
      if (url.includes('/auth/logout')) return jsonResponse({}, 200);
      return jsonResponse({}, 404);
    },
  );
  global.fetch = fetchMock;
  return fetchMock;
}

function renderShell() {
  return render(
    <Providers>
      <AppShell>
        <div>Dashboard body</div>
      </AppShell>
    </Providers>,
  );
}

describe('AppShell', () => {
  beforeEach(() => {
    replaceMock.mockClear();
    pushMock.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the children passed to it', async () => {
    mockFetch();

    renderShell();

    expect(await screen.findByText('Dashboard body')).toBeInTheDocument();
  });

  it('shows Dashboard (/), Content (/content) and Connected apps (/connected-apps) nav links by role and accessible name', async () => {
    mockFetch();

    renderShell();

    await screen.findByText('Dashboard body');
    expect(screen.getByRole('link', { name: 'Dashboard' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: 'Content' })).toHaveAttribute('href', '/content');
    expect(screen.getByRole('link', { name: 'Connected apps' })).toHaveAttribute(
      'href',
      '/connected-apps',
    );
  });

  it("surfaces the signed-in user's name from the Me query (via the store) in the account menu", async () => {
    mockFetch();

    renderShell();

    expect(await screen.findByRole('button', { name: /Ada Lovelace/i })).toBeInTheDocument();
  });

  it('activating Sign out POSTs /api/v1/auth/logout with credentials, then redirects to /signin', async () => {
    const fetchMock = mockFetch();
    const user = userEvent.setup();

    renderShell();

    const menuTrigger = await screen.findByRole('button', { name: /Ada Lovelace/i });
    await user.click(menuTrigger);

    const signOutItem = await screen.findByRole('menuitem', { name: /sign out/i });
    await user.click(signOutItem);

    await waitFor(() => {
      const logoutCall = fetchMock.mock.calls.find(([input]) =>
        requestUrl(input).includes('/auth/logout'),
      );
      expect(logoutCall).toBeDefined();
      // Read method/credentials from the `Request` itself when that's the
      // calling convention, else from `init` — same pin (POST, credentials
      // include) either way.
      const [logoutInput, logoutInit] = logoutCall!;
      const method = logoutInput instanceof Request ? logoutInput.method : logoutInit?.method;
      const credentials =
        logoutInput instanceof Request ? logoutInput.credentials : logoutInit?.credentials;
      expect(method).toBe('POST');
      expect(credentials).toBe('include');
    });

    await waitFor(() => {
      const redirectedToSignin =
        replaceMock.mock.calls.some(([to]) => to === '/signin') ||
        pushMock.mock.calls.some(([to]) => to === '/signin');
      expect(redirectedToSignin).toBe(true);
    });
  });
});
