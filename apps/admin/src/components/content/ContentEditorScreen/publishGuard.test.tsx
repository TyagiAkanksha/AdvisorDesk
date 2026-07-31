// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import type { ContentDto } from '@/types/api/content';

import { ContentEditorScreen } from '.';

// fix round 1, F2 (Important — probe-confirmed): Publish used to POST /publish immediately, so
// an in-progress unsaved edit never reached the server before phase-3 embeds the STORED body —
// publishing the STALE version. Chosen semantics (controller decision): SAVE-THEN-PUBLISH — a
// dirty editor PATCHes first; publish only fires after that PATCH succeeds; a PATCH failure
// surfaces via the existing snackbar and publish never fires. Archive is untouched (it doesn't
// embed anything).
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

async function requestJson(input: RequestInfo | URL): Promise<unknown> {
  if (input instanceof Request) {
    return input.clone().json();
  }
  return undefined;
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

interface MockFetchOptions {
  updateContentResponse?: Response;
}

function mockFetch(options: MockFetchOptions = {}) {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
    async (input, init) => {
      const pathname = pathnameOf(input);
      const method = requestMethod(input, init);

      if (pathname.endsWith('/publish') && method === 'POST') {
        return jsonResponse({ ...draftFixture, status: 'published' });
      }
      if (pathname === `/api/v1/content/${draftFixture.id}` && method === 'GET') {
        return jsonResponse(draftFixture);
      }
      if (pathname === `/api/v1/content/${draftFixture.id}` && method === 'PATCH') {
        return options.updateContentResponse ?? jsonResponse({ ...draftFixture, title: 'Changed' });
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
      <ContentEditorScreen contentId={draftFixture.id} />
    </Providers>,
  );
}

describe('ContentEditorScreen save-then-publish', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('dirty editor: clicking Publish PATCHes the changed fields, then POSTs /publish — in that order, exactly once each', async () => {
    const fetchMock = mockFetch();
    const user = userEvent.setup();

    renderEdit();

    const titleInput = await screen.findByRole('textbox', { name: /title/i });
    await user.clear(titleInput);
    await user.type(titleInput, 'Changed Title');

    await user.click(screen.getByRole('button', { name: /publish/i }));

    await waitFor(() => {
      const publishCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          pathnameOf(input) === `/api/v1/content/${draftFixture.id}/publish` &&
          requestMethod(input, init) === 'POST',
      );
      expect(publishCall).toBeDefined();
    });

    const patchCalls = fetchMock.mock.calls.filter(
      ([input, init]) =>
        pathnameOf(input) === `/api/v1/content/${draftFixture.id}` &&
        requestMethod(input, init) === 'PATCH',
    );
    const publishCalls = fetchMock.mock.calls.filter(
      ([input, init]) =>
        pathnameOf(input) === `/api/v1/content/${draftFixture.id}/publish` &&
        requestMethod(input, init) === 'POST',
    );
    expect(patchCalls).toHaveLength(1);
    expect(publishCalls).toHaveLength(1);

    const patchBody = (await requestJson(patchCalls[0][0])) as Record<string, unknown>;
    expect(patchBody).toEqual({ title: 'Changed Title' });

    const patchIndex = fetchMock.mock.calls.indexOf(patchCalls[0]);
    const publishIndex = fetchMock.mock.calls.indexOf(publishCalls[0]);
    expect(patchIndex).toBeGreaterThanOrEqual(0);
    expect(publishIndex).toBeGreaterThan(patchIndex);
  });

  it('a PATCH failure blocks publish entirely — no POST /publish fires, and the failure is shown as an alert', async () => {
    const FAILURE_MESSAGE = 'Could not save due to a validation conflict.';
    const fetchMock = mockFetch({
      updateContentResponse: jsonResponse(
        { error: { code: 'conflict', message: FAILURE_MESSAGE } },
        500,
      ),
    });
    const user = userEvent.setup();

    renderEdit();

    const titleInput = await screen.findByRole('textbox', { name: /title/i });
    await user.clear(titleInput);
    await user.type(titleInput, 'Changed Title');

    await user.click(screen.getByRole('button', { name: /publish/i }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(FAILURE_MESSAGE);

    const publishCalls = fetchMock.mock.calls.filter(
      ([input, init]) =>
        pathnameOf(input) === `/api/v1/content/${draftFixture.id}/publish` &&
        requestMethod(input, init) === 'POST',
    );
    expect(publishCalls).toHaveLength(0);
  });

  // fix round 2, N3 (folded Minor): before this round, `isTransitioning` (the Publish button's
  // `disabled` guard) never accounted for `isSaving` — so the save-then-publish PATCH this
  // round's F2 introduced ran with Publish still clickable, and a fast double-click fired
  // PATCH -> PATCH -> PUBLISH -> PUBLISH (two stale-body embeds from phase 3). Two synchronous
  // `fireEvent.click`s (rather than two awaited `user.click`s, which would let a render commit
  // — and the `disabled` attribute apply — in between) is what actually exercises the race.
  it('double-clicking Publish on a dirty editor still fires exactly one PATCH and one POST /publish', async () => {
    const fetchMock = mockFetch();
    const user = userEvent.setup();

    renderEdit();

    const titleInput = await screen.findByRole('textbox', { name: /title/i });
    await user.clear(titleInput);
    await user.type(titleInput, 'Changed Title');

    const publishButton = screen.getByRole('button', { name: /publish/i });
    fireEvent.click(publishButton);
    fireEvent.click(publishButton);

    await waitFor(() => {
      const publishCalls = fetchMock.mock.calls.filter(
        ([input, init]) =>
          pathnameOf(input) === `/api/v1/content/${draftFixture.id}/publish` &&
          requestMethod(input, init) === 'POST',
      );
      expect(publishCalls).toHaveLength(1);
    });

    const patchCalls = fetchMock.mock.calls.filter(
      ([input, init]) =>
        pathnameOf(input) === `/api/v1/content/${draftFixture.id}` &&
        requestMethod(input, init) === 'PATCH',
    );
    expect(patchCalls).toHaveLength(1);
  });
});
