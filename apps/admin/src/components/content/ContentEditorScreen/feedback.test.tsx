// @vitest-environment jsdom
import { render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import type { ContentDto } from '@/types/api/content';

import { ContentEditorScreen } from '.';

// Task 19 (C5, hook half): every mutation now reports through the global `useSnackbar()`
// instead of the editor's own (now-deleted) `AppSnackbar` — this is a NEW, colocated
// one-behaviour file per this folder's convention (Component.test.tsx and the other pinned
// files stay unmodified). RED today: `AppSnackbar` here only ever rendered `severity="error"`
// (`role="alert"`), so there is no `role="status"` success notice anywhere yet.
//
// Fixtures/helpers below are copied from useContentEditor.test.tsx (same folder) per the brief,
// plus `renderEdit`/`renderNew` copied from the pinned Component.test.tsx (they wrap the screen
// in `Providers`). The `Handler` type is kept simplified to `(url, method) => Response` here
// too, for consistency with useContentEditor.test.tsx.
const pushMock = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn() }),
}));

function requestUrl(input: RequestInfo | URL): string {
  return input instanceof Request ? input.url : String(input);
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return input instanceof Request ? input.method : (init?.method ?? 'GET');
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const draftFixture: ContentDto = {
  author_id: null,
  body_md: '# Roth IRA Conversion Basics\n\nBody.',
  created_at: '2026-01-01T12:00:00Z',
  id: '11111111-1111-1111-1111-111111111111',
  published_at: null,
  slug: 'roth-ira-conversion-basics',
  status: 'draft',
  tags: ['tax-planning'],
  title: 'Roth IRA Conversion Basics',
  updated_at: '2026-03-15T12:00:00Z',
  updated_by: null,
};

type Handler = (url: URL, method: string) => Response | Promise<Response>;

function mockFetch(handler: Handler) {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
    async (input, init) => handler(new URL(requestUrl(input)), requestMethod(input, init)),
  );
  global.fetch = fetchMock;
  return fetchMock;
}

const editHandler: Handler = (url, method) => {
  if (url.pathname === `/api/v1/content/${draftFixture.id}` && method === 'GET')
    return jsonResponse(draftFixture);
  if (url.pathname === `/api/v1/content/${draftFixture.id}` && method === 'PATCH')
    return jsonResponse(draftFixture);
  if (url.pathname === '/api/v1/tags')
    return jsonResponse([
      { id: 't1', name: 'retirement', count: 2 },
      { id: 't2', name: 'tax-planning', count: 1 },
    ]);
  return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
};

function renderNew() {
  return render(
    <Providers>
      <ContentEditorScreen />
    </Providers>,
  );
}

function renderEdit(contentId: string) {
  return render(
    <Providers>
      <ContentEditorScreen contentId={contentId} />
    </Providers>,
  );
}

describe('ContentEditorScreen mutation feedback (global snackbar)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    pushMock.mockClear();
  });

  it('a successful Save shows a "Saved" notice', async () => {
    mockFetch(editHandler);
    const user = userEvent.setup();

    renderEdit(draftFixture.id);
    const titleInput = await screen.findByRole('textbox', { name: /title/i });
    await user.clear(titleInput);
    await user.type(titleInput, 'Changed');
    await user.click(screen.getByRole('button', { name: /save/i }));

    expect(await screen.findByRole('status')).toHaveTextContent('Saved');
  });

  it('a successful Publish shows a "Published" notice (and not a "Saved" one)', async () => {
    mockFetch((url, method) => {
      if (url.pathname === `/api/v1/content/${draftFixture.id}/publish` && method === 'POST') {
        return jsonResponse({
          ...draftFixture,
          status: 'published',
          published_at: '2026-03-16T12:00:00Z',
        });
      }
      return editHandler(url, method);
    });
    const user = userEvent.setup();

    renderEdit(draftFixture.id);
    await user.click(await screen.findByRole('button', { name: /publish/i }));

    const status = await screen.findByRole('status');
    expect(status).toHaveTextContent('Published');
    expect(status).not.toHaveTextContent('Saved');
  });

  it('a successful Create shows "Saved" and routes to the new item', async () => {
    mockFetch((url, method) => {
      if (url.pathname === '/api/v1/content' && method === 'POST') {
        return jsonResponse({ ...draftFixture, id: '22222222-2222-2222-2222-222222222222' }, 201);
      }
      return editHandler(url, method);
    });
    const user = userEvent.setup();

    renderNew();
    await user.type(screen.getByRole('textbox', { name: /title/i }), 'New Piece');
    await user.click(screen.getByRole('button', { name: /create/i }));

    expect(await screen.findByRole('status')).toHaveTextContent('Saved');
    await waitFor(() =>
      expect(pushMock).toHaveBeenCalledWith('/content/22222222-2222-2222-2222-222222222222'),
    );
  });

  it('a confirmed Delete shows "Deleted" and routes to the list', async () => {
    mockFetch((url, method) => {
      if (url.pathname === `/api/v1/content/${draftFixture.id}` && method === 'DELETE') {
        return new Response(null, { status: 204 });
      }
      return editHandler(url, method);
    });
    const user = userEvent.setup();

    renderEdit(draftFixture.id);
    await user.click(await screen.findByRole('button', { name: /delete/i }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: /delete/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/content'));
    expect(await screen.findByRole('status')).toHaveTextContent('Deleted');
  });
});
