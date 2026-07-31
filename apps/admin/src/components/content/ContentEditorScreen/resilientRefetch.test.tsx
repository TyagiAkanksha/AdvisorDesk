// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import type { ContentDto } from '@/types/api/content';

import { ContentEditorScreen } from '.';

// fix round 1, F3 (Important): a failed BACKGROUND refetch (e.g. the tag-invalidation-driven
// `getContent` refetch RTK Query issues right after a successful Save, since `updateContent`
// and `getContent` share the `'Content'` tag) used to unconditionally render `ErrorState`
// instead of the form — unmounting it and discarding whatever the admin was mid-typing. The fix
// only falls back to `ErrorState` when there is genuinely nothing cached to show; otherwise the
// form stays mounted and the refetch failure surfaces through the snackbar instead.
//
// Mocking conventions mirror the pinned Component.test.tsx in this same folder exactly
// (docs/FRONTEND-CONVENTIONS.md §7 — mock only the network edge + next/navigation seam).
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

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

const draftFixture: ContentDto = {
  author_id: null,
  body_md: '# Roth IRA Conversion Basics',
  created_at: '2026-01-01T00:00:00Z',
  id: '11111111-1111-1111-1111-111111111111',
  published_at: null,
  slug: 'roth-ira-conversion-basics',
  status: 'draft',
  tags: ['tax-planning'],
  title: 'Roth IRA Conversion Basics',
  updated_at: '2026-01-02T00:00:00Z',
  updated_by: null,
};

function mockFetch() {
  let getCalls = 0;
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
    async (input, init) => {
      const pathname = pathnameOf(input);
      const method = requestMethod(input, init);

      if (pathname === `/api/v1/content/${draftFixture.id}` && method === 'GET') {
        getCalls += 1;
        // First GET (initial mount) succeeds; every GET after that (the background refetch
        // triggered by the successful PATCH's tag invalidation) fails.
        if (getCalls === 1) {
          return jsonResponse(draftFixture);
        }
        return jsonResponse({ error: { code: 'internal_error', message: 'Refresh failed.' } }, 500);
      }
      if (pathname === `/api/v1/content/${draftFixture.id}` && method === 'PATCH') {
        return jsonResponse({ ...draftFixture, title: 'Changed Title' });
      }
      if (pathname === '/api/v1/tags' && method === 'GET') {
        return jsonResponse([]);
      }
      return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
    },
  );
  global.fetch = fetchMock;
  return { fetchMock, getCallCount: () => getCalls };
}

function renderEdit() {
  return render(
    <Providers>
      <ContentEditorScreen contentId={draftFixture.id} />
    </Providers>,
  );
}

describe('ContentEditorScreen resilient background refetch', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('a failed background refetch after a successful Save keeps the form mounted with typed values intact, and surfaces the failure as an alert', async () => {
    const { getCallCount } = mockFetch();
    const user = userEvent.setup();

    renderEdit();

    const titleInput = await screen.findByRole('textbox', { name: /title/i });
    await user.clear(titleInput);
    await user.type(titleInput, 'Changed Title');

    await user.click(screen.getByRole('button', { name: /save/i }));

    // The PATCH's success invalidates the `'Content'` tag; `getContent` (still subscribed)
    // refetches on its own and this second GET is the one mocked to 500.
    await waitFor(() => expect(getCallCount()).toBeGreaterThanOrEqual(2));

    // Non-destructive: the form is still here, and the title field still holds what the admin
    // typed — never blanked, never replaced by ErrorState.
    expect(screen.getByRole('textbox', { name: /title/i })).toHaveValue('Changed Title');
    expect(screen.queryByText("Couldn't load this item.")).not.toBeInTheDocument();

    const alert = await screen.findByRole('alert');
    expect(alert).toBeVisible();
    expect(alert.textContent?.trim().length).toBeGreaterThan(0);
  });

  // fix round 2, N2 (Important, blocking — re-review regression on this round's own F3 fix):
  // `displayedSnackbarMessage` re-derived the alert from `isError && hasContent` on every
  // render, so `closeSnackbar` (which only cleared the unrelated explicit `snackbarMessage`
  // state) had no effect on it — zero escape hatches (Close, auto-hide, and clickaway all
  // failed to dismiss it; clickaway was already correctly a no-op from this round's M2, which
  // made the missing Close/auto-hide path show up as the alert being permanently stuck).
  it('clicking Close dismisses the background-refetch alert; a later, distinct failure gets its own alert again', async () => {
    let getCalls = 0;
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async (input, init) => {
        const pathname = pathnameOf(input);
        const method = requestMethod(input, init);

        if (pathname === `/api/v1/content/${draftFixture.id}` && method === 'GET') {
          getCalls += 1;
          // 1: initial mount succeeds. 2: refetch after Save #1 fails (dismissed below).
          // 3: refetch after Save #2 succeeds (clears the failure — and the dismissal with
          // it). 4: refetch after Save #3 fails again — a NEW, distinct failure.
          if (getCalls === 2 || getCalls === 4) {
            return jsonResponse(
              { error: { code: 'internal_error', message: 'Refresh failed.' } },
              500,
            );
          }
          return jsonResponse(draftFixture);
        }
        if (pathname === `/api/v1/content/${draftFixture.id}` && method === 'PATCH') {
          return jsonResponse(draftFixture);
        }
        if (pathname === '/api/v1/tags' && method === 'GET') {
          return jsonResponse([]);
        }
        return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
      },
    );
    global.fetch = fetchMock;
    const user = userEvent.setup();

    renderEdit();

    const titleInput = await screen.findByRole('textbox', { name: /title/i });

    // Save #1 -> PATCH succeeds -> refetch #2 fails -> alert.
    await user.clear(titleInput);
    await user.type(titleInput, 'Edit One');
    await user.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => expect(getCalls).toBeGreaterThanOrEqual(2));
    await screen.findByRole('alert');

    // Dismiss it.
    await user.click(screen.getByRole('button', { name: /close/i }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();

    // Save #2 (still dirty — the failed refetch never wrote a new `content` into the cache) ->
    // PATCH succeeds -> refetch #3 succeeds this time -> `isError` clears, resetting the
    // dismissal flag. No alert reappears just from the refetch finally succeeding.
    await user.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => expect(getCalls).toBeGreaterThanOrEqual(3));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();

    // Edit again + Save #3 -> PATCH succeeds -> refetch #4 fails again: a genuinely NEW
    // failure, not the one already dismissed — it gets shown.
    await user.clear(titleInput);
    await user.type(titleInput, 'Edit Two');
    await user.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => expect(getCalls).toBeGreaterThanOrEqual(4));
    const secondAlert = await screen.findByRole('alert');
    expect(secondAlert).toBeVisible();
  });
});
