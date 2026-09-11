// @vitest-environment jsdom
import { render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import { stubMatchMedia } from '@/testing/matchMedia';
import { navigation } from '@/testing/nextNavigation';

import { AppShell } from '.';

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

describe('AppShell below the md breakpoint', () => {
  let restore: (() => void) | null = null;

  beforeEach(() => {
    navigation.reset('/');
    restore = stubMatchMedia(true);
  });

  afterEach(() => {
    restore?.();
    restore = null;
    vi.restoreAllMocks();
  });

  it('hides the nav behind an "Open navigation" button; it opens on click and closes after navigating', async () => {
    mockFetch();
    const user = userEvent.setup();

    renderShell();
    await screen.findByText('Dashboard body');

    // Closed temporary drawer is `visibility: hidden` (MUI keepMounted) — excluded from role queries.
    expect(screen.queryByRole('navigation', { name: 'Main' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Open navigation' }));
    const nav = await screen.findByRole('navigation', { name: 'Main' });
    expect(within(nav).getByRole('link', { name: 'Content' })).toBeInTheDocument();

    await user.click(within(nav).getByRole('link', { name: 'Content' }));

    await waitFor(() =>
      expect(screen.queryByRole('navigation', { name: 'Main' })).not.toBeInTheDocument(),
    );
  });

  it('the agent drawer is full-width on phones', async () => {
    mockFetch();
    const user = userEvent.setup();

    renderShell();
    await screen.findByText('Dashboard body');
    await user.click(screen.getByRole('button', { name: 'Agent' }));

    const panel = document.getElementById('app-shell-agent-panel');
    expect(panel).not.toBeNull();
    // jsdom resolves `100vw` to pixels (sub-phase A lesson) — assert the paper is as wide as the
    // viewport rather than pinning the unit.
    const paper = panel!.querySelector('.MuiDrawer-paper');
    expect(paper).toHaveStyle({ width: `${window.innerWidth}px` });
  });
});
