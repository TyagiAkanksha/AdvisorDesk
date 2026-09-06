// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';

import { AppShell } from '.';

// 6R task-11, WR-13 (AppShell accessible-name gap, flagged twice, fixed never): the Agent-panel
// toggle and the account-menu trigger are both disclosure buttons (each shows/hides something on
// click) but expose neither `aria-expanded` nor `aria-haspopup` today. Root cause (brief):
// `common/Button`'s `ButtonProps` interface is closed — no aria-* passthrough — so
// `AppShell/Component.tsx` has no way to wire these even if it tried.
//
// This is a NEW, colocated one-behavior file — the existing pinned `Component.test.tsx` and
// `agentPanelToggle.test.tsx` in this folder are untouched (same convention already used by
// `ContentListScreen/{pagination,deleteError,newContentLink,resilientRefetch}.test.tsx`).
//
// RED today: BEHAVIORAL — both buttons already render, but neither carries `aria-haspopup` at
// all, and neither carries `aria-expanded` in either state, so every assertion below fails
// against today's DOM.
//
// Judgment call (test-author): pinning only `aria-expanded` (exact closed/open string value) and
// `aria-haspopup` (bare presence, not a specific token) — the brief's own "Test-author pins" line
// for WR-13 names exactly these two, not `aria-controls` (which needs a target id the implementer
// hasn't chosen yet, so it is left to the implementer/reviewer rather than pinned here). WR-66
// (avatar `alt=""`/aria-hidden — the ride-along Minor named in the same brief section) is outside
// this dispatch's stated deliverable list and is not tested here.
const replaceMock = vi.fn();
const pushMock = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: replaceMock, push: pushMock }),
}));

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

function mockFetch() {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
    async (input) => {
      const url = requestUrl(input);
      if (url.includes('/auth/me')) return jsonResponse(meFixture, 200);
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

describe('AppShell trigger ARIA (WR-13)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('the Agent-panel toggle has aria-haspopup and aria-expanded that flips false -> true on click', async () => {
    mockFetch();
    const user = userEvent.setup();

    renderShell();
    await screen.findByText('Dashboard body');

    const toggle = screen.getByRole('button', { name: 'Agent' });
    expect(toggle).toHaveAttribute('aria-haspopup');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');

    await user.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'true');
  });

  it('the account-menu trigger has aria-haspopup and aria-expanded that flips false -> true on click', async () => {
    mockFetch();
    const user = userEvent.setup();

    renderShell();

    const menuTrigger = await screen.findByRole('button', { name: /Ada Lovelace/i });
    expect(menuTrigger).toHaveAttribute('aria-haspopup');
    expect(menuTrigger).toHaveAttribute('aria-expanded', 'false');

    await user.click(menuTrigger);

    await waitFor(() => {
      expect(menuTrigger).toHaveAttribute('aria-expanded', 'true');
    });
  });
});
