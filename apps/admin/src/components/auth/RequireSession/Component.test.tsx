// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';

import { RequireSession } from '.';

// task-04 / PRD §5.1: RequireSession rehydrates the admin session from
// `GET /api/v1/auth/me` and gates its children on that result. Mock ONLY the
// network edge (fetch) and the next/navigation framework seam
// (docs/FRONTEND-CONVENTIONS.md §7) — everything else (RequireSession,
// baseApi, authApi, the store, Providers) is the real, unmocked module tree.
const replaceMock = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: replaceMock, push: vi.fn() }),
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

function renderGuard() {
  return render(
    <Providers>
      <RequireSession>
        <div>Protected content</div>
      </RequireSession>
    </Providers>,
  );
}

describe('RequireSession', () => {
  beforeEach(() => {
    replaceMock.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders no children and does not redirect while the /auth/me session query is loading', () => {
    // A fetch that never resolves keeps the RTK Query `getMe` call in its
    // loading state for the lifetime of the test.
    global.fetch = vi.fn(() => new Promise<Response>(() => {}));

    renderGuard();

    expect(screen.queryByText('Protected content')).not.toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it('redirects to /signin and never renders children when /auth/me responds 401', async () => {
    global.fetch = vi.fn(async () =>
      jsonResponse({ error: { code: 'unauthorized', message: 'Authentication required.' } }, 401),
    );

    renderGuard();

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith('/signin');
    });
    expect(screen.queryByText('Protected content')).not.toBeInTheDocument();
  });

  it('renders children once /auth/me succeeds with a MeResponse, without redirecting', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(meFixture, 200));
    global.fetch = fetchMock;

    renderGuard();

    expect(await screen.findByText('Protected content')).toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalled();

    // baseApi must send the HttpOnly session cookie (PRD §9 / task-04 Interfaces):
    // pin `credentials: 'include'` on the /auth/me request.
    const meCall = fetchMock.mock.calls.find(([input]) => String(input).includes('/auth/me'));
    expect(meCall).toBeDefined();
    expect(meCall?.[1]).toMatchObject({ credentials: 'include' });
  });
});
