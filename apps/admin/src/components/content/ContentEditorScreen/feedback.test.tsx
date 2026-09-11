// @vitest-environment jsdom
import { screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  draftFixture,
  editHandler,
  jsonResponse,
  mockEditorFetchWith as mockFetch,
  publishedFixture,
  renderEdit,
  renderNew,
} from './testing/renderEditor';
import type { EditorFetchHandler } from './testing/renderEditor';

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

const publishedHandler: EditorFetchHandler = (url, method) => {
  if (url.pathname === `/api/v1/content/${publishedFixture.id}` && method === 'GET') {
    return jsonResponse(publishedFixture);
  }
  if (url.pathname === `/api/v1/content/${publishedFixture.id}/archive` && method === 'POST') {
    return jsonResponse({ ...publishedFixture, status: 'archived' });
  }
  return editHandler(url, method);
};

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

  it('a successful Archive shows an "Archived" notice', async () => {
    mockFetch(publishedHandler);
    const user = userEvent.setup();

    renderEdit(publishedFixture.id);
    await user.click(await screen.findByRole('button', { name: /archive/i }));

    expect(await screen.findByRole('status')).toHaveTextContent('Archived');
  });

  it('a failed Archive surfaces the envelope message as an alert and shows no success notice', async () => {
    const ARCHIVE_FAILURE_MESSAGE = 'Could not archive while a publish is in flight.';
    mockFetch((url, method) => {
      if (url.pathname === `/api/v1/content/${publishedFixture.id}/archive` && method === 'POST') {
        return jsonResponse({ error: { code: 'conflict', message: ARCHIVE_FAILURE_MESSAGE } }, 409);
      }
      return publishedHandler(url, method);
    });
    const user = userEvent.setup();

    renderEdit(publishedFixture.id);
    await user.click(await screen.findByRole('button', { name: /archive/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(ARCHIVE_FAILURE_MESSAGE);
    expect(screen.queryByText('Archived')).not.toBeInTheDocument();
  });
});
