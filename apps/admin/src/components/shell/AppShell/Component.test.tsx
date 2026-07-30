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

function mockFetch(): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes('/auth/me')) return jsonResponse(meFixture, 200);
    if (url.includes('/auth/logout')) return jsonResponse({}, 200);
    return jsonResponse({}, 404);
  });
  global.fetch = fetchMock as unknown as typeof fetch;
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

  it('shows Dashboard (href /) and Content (href /content) nav links by role and accessible name', async () => {
    mockFetch();

    renderShell();

    await screen.findByText('Dashboard body');
    expect(screen.getByRole('link', { name: 'Dashboard' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: 'Content' })).toHaveAttribute('href', '/content');
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
        String(input).includes('/auth/logout'),
      );
      expect(logoutCall).toBeDefined();
      expect(logoutCall?.[1]).toMatchObject({ method: 'POST', credentials: 'include' });
    });

    await waitFor(() => {
      const redirectedToSignin =
        replaceMock.mock.calls.some(([to]) => to === '/signin') ||
        pushMock.mock.calls.some(([to]) => to === '/signin');
      expect(redirectedToSignin).toBe(true);
    });
  });
});
