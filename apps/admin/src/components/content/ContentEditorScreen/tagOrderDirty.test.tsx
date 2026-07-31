// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import type { ContentDto } from '@/types/api/content';

import { ContentEditorScreen } from '.';

// fix round 1, F4 (Important): the server always returns `tags` sorted alphabetically
// (app.services.tags), but the old `tagsEqual` compared positionally — so as soon as a save's
// refetch echoed the same tag set back in a different (sorted) order, the editor stayed
// "phantom dirty" forever (Save never re-disabled; every further click re-PATCHed and
// re-published a body that hadn't actually changed). The fix compares sorted copies while still
// sending the user's own array, untouched, to the server.
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

// Deliberately NOT alphabetically sorted — mirrors a record whose tags were assembled by
// appending at the end (client behavior) rather than by the server's own alphabetical sort.
const initialFixture: ContentDto = {
  author_id: null,
  body_md: '# Roth IRA Conversion Basics',
  created_at: '2026-01-01T00:00:00Z',
  id: '11111111-1111-1111-1111-111111111111',
  published_at: null,
  slug: 'roth-ira-conversion-basics',
  status: 'draft',
  tags: ['tax-planning', 'retirement'],
  title: 'Roth IRA Conversion Basics',
  updated_at: '2026-01-02T00:00:00Z',
  updated_by: null,
};

// What the server answers after the save: same tag SET, alphabetically sorted (its own
// normalization), plus the title change that was actually requested.
const afterSaveFixture: ContentDto = {
  ...initialFixture,
  tags: ['retirement', 'tax-planning'],
  title: 'Changed Title',
};

function mockFetch() {
  let getCalls = 0;
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
    async (input, init) => {
      const pathname = pathnameOf(input);
      const method = requestMethod(input, init);

      if (pathname === `/api/v1/content/${initialFixture.id}` && method === 'GET') {
        getCalls += 1;
        return jsonResponse(getCalls === 1 ? initialFixture : afterSaveFixture);
      }
      if (pathname === `/api/v1/content/${initialFixture.id}` && method === 'PATCH') {
        return jsonResponse(afterSaveFixture);
      }
      if (pathname === '/api/v1/tags' && method === 'GET') {
        return jsonResponse([]);
      }
      return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
    },
  );
  global.fetch = fetchMock;
  return fetchMock;
}

function renderEdit() {
  return render(
    <Providers>
      <ContentEditorScreen contentId={initialFixture.id} />
    </Providers>,
  );
}

describe('ContentEditorScreen tag-order-insensitive dirty tracking', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('Save re-disables after a refetch echoes the same tags back sorted alphabetically', async () => {
    mockFetch();
    const user = userEvent.setup();

    renderEdit();

    const titleInput = await screen.findByRole('textbox', { name: /title/i });
    await user.clear(titleInput);
    await user.type(titleInput, 'Changed Title');

    const saveButton = screen.getByRole('button', { name: /save/i });
    expect(saveButton).toBeEnabled();
    await user.click(saveButton);

    // Once the PATCH succeeds and the tag-invalidation-driven refetch lands (`content.tags`
    // now `['retirement', 'tax-planning']` vs. the editor's still-untouched local `tags` state
    // `['tax-planning', 'retirement']`), title and tags both match again — Save must go back to
    // disabled, not stay phantom-dirty.
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save/i })).toBeDisabled();
    });
  });
});
