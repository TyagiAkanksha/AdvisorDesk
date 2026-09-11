// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import { navigation } from '@/testing/nextNavigation';

import { AppShell } from '.';

// phase-5 task-04 (admin agent panel), RED (TDD), Step 5 test 6: "AppShell toggle opens the
// panel". `AppShell/Component.tsx` and `AppShell/Component.test.tsx` are EXISTING pinned files
// this task's binding rules forbid modifying — this is instead a NEW, colocated test file, the
// same convention already used in this codebase for one-behavior-per-file additions alongside an
// existing folder's `Component.test.tsx` (e.g.
// `apps/admin/src/components/content/ContentListScreen/{pagination,deleteError,
// newContentLink,resilientRefetch}.test.tsx`, none of which edit that folder's own
// `Component.test.tsx`).
//
// Brief: docs/plans/phase-5-mcp-agent/task-04-admin-agent-panel.md, Files ("Modify:
// apps/admin/src/components/shell/AppShell/Component.tsx (panel toggle button + Drawer mount)"),
// Interfaces ("AgentPanel: persistent right MUI Drawer toggled from the AppShell").
//
// RED mode: BEHAVIORAL, not module-resolution — `AppShell` already exists and renders today
// (unmodified); this test fails because today's AppShell has no agent-panel toggle button at all
// (`getByRole('button', {name: 'Agent'})` finds nothing).
//
// Judgment call (test-author): the toggle's accessible name ("Agent") and the panel's "Message"
// textbox are both invented pins (the brief specifies "toggle button + Drawer mount" but no
// literal accessible names) — reused verbatim from
// `apps/agent/useAgentStream.test.tsx`/`AgentPanel/Component.test.tsx`'s own "Message"/"Send"
// pins (themselves modeled on `apps/client/src/components/chat/ChatScreen/Component.test.tsx`'s
// precedent) for one consistent contract across every file that touches the agent panel. This
// test does NOT assert the panel/textbox is ABSENT before the toggle is clicked: `AgentPanel`
// needs to stay mounted (not just visually hidden) across the toggle so its `useAgentStream`
// conversation state survives, and MUI's non-permanent `Drawer` variants keep their children in
// the DOM (transformed off-screen, not `display:none`) while closed — asserting "absent
// beforehand" would therefore couple this test to an implementation detail (whether/how the
// implementer hides a closed panel) rather than the one thing the brief actually pins: clicking
// the toggle opens it.

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

describe('AppShell agent panel toggle', () => {
  beforeEach(() => {
    navigation.reset('/');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('clicking the "Agent" toggle in the app bar opens the agent panel', async () => {
    mockFetch();
    const user = userEvent.setup();

    renderShell();
    await screen.findByText('Dashboard body');

    const toggle = screen.getByRole('button', { name: 'Agent' });
    await user.click(toggle);

    expect(await screen.findByRole('textbox', { name: 'Message' })).toBeInTheDocument();
  });
});
