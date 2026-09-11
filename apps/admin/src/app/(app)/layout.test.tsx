// @vitest-environment jsdom
import { render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import { navigation } from '@/testing/nextNavigation';

import Layout from './layout';

// hygiene t05 (p8 final X4): the authenticated layout paints the shell chrome BEFORE the
// session query resolves; the gate's loading / redirect / error states live inside <main>.
// Mock ONLY fetch and the next/navigation seam (docs/FRONTEND-CONVENTIONS.md §7).
vi.mock('next/navigation', () => import('@/testing/nextNavigation'));

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

function requestUrl(input: RequestInfo | URL): string {
  return input instanceof Request ? input.url : String(input);
}

function mockMe(respond: () => Promise<Response>) {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
    async (input) => {
      if (requestUrl(input).includes('/auth/me')) return respond();
      return jsonResponse({}, 404);
    },
  );
  global.fetch = fetchMock;
  return fetchMock;
}

function renderLayout() {
  return render(
    <Providers>
      <Layout>
        <div>Page body</div>
      </Layout>
    </Providers>,
  );
}

function expectShellChrome() {
  expect(screen.getByRole('banner')).toBeInTheDocument();
  expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'AdvisorDesk Admin' })).toHaveAttribute('href', '/');
}

describe('(app) layout', () => {
  beforeEach(() => {
    navigation.reset('/');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the shell chrome and a loading indicator inside main while /auth/me is pending — not the page', () => {
    mockMe(() => new Promise<Response>(() => {}));

    renderLayout();

    expectShellChrome();
    const main = screen.getByRole('main');
    expect(within(main).getByRole('progressbar')).toBeInTheDocument();
    expect(screen.queryByText('Page body')).not.toBeInTheDocument();
    expect(navigation.replace).not.toHaveBeenCalled();
  });

  it('keeps the shell chrome and redirects to /signin on a 401, never rendering the page', async () => {
    mockMe(async () =>
      jsonResponse({ error: { code: 'unauthorized', message: 'Authentication required.' } }, 401),
    );

    renderLayout();

    await waitFor(() => {
      expect(navigation.replace).toHaveBeenCalledWith('/signin');
    });
    expectShellChrome();
    expect(screen.queryByText('Page body')).not.toBeInTheDocument();
  });

  it('renders a session error state inside main (shell still up) when /auth/me fails for another reason', async () => {
    mockMe(async () => jsonResponse({ error: { code: 'internal', message: 'boom' } }, 500));

    renderLayout();

    const main = screen.getByRole('main');
    expect(
      await within(main).findByText("Couldn't verify your session. Please try again."),
    ).toBeInTheDocument();
    expectShellChrome();
    expect(navigation.replace).not.toHaveBeenCalled();
    expect(screen.queryByText('Page body')).not.toBeInTheDocument();
  });

  it('renders the page inside main once /auth/me succeeds, with the account menu in the bar', async () => {
    const fetchMock = mockMe(async () => jsonResponse(meFixture, 200));

    renderLayout();

    const main = screen.getByRole('main');
    expect(await within(main).findByText('Page body')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Ada Lovelace/ })).toBeInTheDocument();
    expect(navigation.replace).not.toHaveBeenCalled();
    // hygiene final B4: RequireSession and AppShell both call useGetMeQuery() — RTK Query must
    // dedupe the two subscribers into a single network request.
    expect(
      fetchMock.mock.calls.filter(([input]) => requestUrl(input).includes('/auth/me')),
    ).toHaveLength(1);
  });
});
