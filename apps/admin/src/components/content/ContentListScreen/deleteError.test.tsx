// @vitest-environment jsdom
import { render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import { navigation } from '@/testing/nextNavigation';
import type { ContentDto, ContentListDto } from '@/types/api/content';

import { ContentListScreen } from '.';

vi.mock('next/navigation', () => import('@/testing/nextNavigation'));

// fix round 1, F2 (a DELETE 500 used to leave the dialog open with zero feedback — a bare
// `catch {}`). Mock ONLY the network edge (docs/FRONTEND-CONVENTIONS.md §7).
//
// Request-aware fetch mocking (task-04 review lesson, mirrored from the pinned
// Component.test.tsx in this same folder): `fetchBaseQuery` hands the mocked `fetch` a native
// `Request`, which stringifies to `"[object Request]"` — resolve the real URL off the
// `Request` itself, not `String(input)`.
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

const itemA: ContentDto = {
  author_id: null,
  body_md: '# Roth IRA Conversion Basics',
  created_at: '2026-01-01T00:00:00Z',
  id: '11111111-1111-1111-1111-111111111111',
  published_at: null,
  slug: 'roth-ira-conversion-basics',
  status: 'draft',
  tags: [],
  title: 'Roth IRA Conversion Basics',
  updated_at: '2026-03-15T00:00:00Z',
  updated_by: null,
};

const listFixture: ContentListDto = {
  items: [itemA],
  page: 1,
  page_size: 20,
  total: 1,
};

const DELETE_FAILURE_MESSAGE = 'Could not delete due to a database hiccup.';

function renderScreen() {
  return render(
    <Providers>
      <ContentListScreen />
    </Providers>,
  );
}

describe('ContentListScreen delete-error surfacing', () => {
  beforeEach(() => {
    navigation.reset('/content');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('a DELETE 500 with an envelope body keeps the dialog open and shows the message as an alert; retrying then succeeds', async () => {
    let deleteAttempts = 0;
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async (input, init) => {
        const pathname = pathnameOf(input);
        const method = requestMethod(input, init);

        if (pathname === '/api/v1/content' && method === 'GET') {
          return jsonResponse(listFixture);
        }
        if (pathname.startsWith('/api/v1/content/') && method === 'DELETE') {
          deleteAttempts += 1;
          if (deleteAttempts === 1) {
            return jsonResponse(
              { error: { code: 'internal_error', message: DELETE_FAILURE_MESSAGE } },
              500,
            );
          }
          return new Response(null, { status: 204 });
        }
        return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
      },
    );
    global.fetch = fetchMock;
    const user = userEvent.setup();

    renderScreen();
    await screen.findByRole('row', { name: new RegExp(itemA.title) });

    const deleteButton = screen.getByRole('button', {
      name: new RegExp(`delete.*${itemA.title}`, 'i'),
    });
    await user.click(deleteButton);

    const dialog = await screen.findByRole('dialog');
    const confirmButton = within(dialog).getByRole('button', { name: /delete/i });
    await user.click(confirmButton);

    // The failed DELETE fired...
    await waitFor(() => expect(deleteAttempts).toBe(1));
    // ...and the envelope's message is now visible inside the still-open dialog as an alert
    // (never a raw error body — docs/FRONTEND-CONVENTIONS.md §9).
    const alert = await within(dialog).findByRole('alert');
    expect(alert).toHaveTextContent(DELETE_FAILURE_MESSAGE);
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    // Retry: clicking Confirm again re-issues the DELETE; this time it succeeds and the
    // dialog closes.
    await user.click(within(dialog).getByRole('button', { name: /delete/i }));

    await waitFor(() => expect(deleteAttempts).toBe(2));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });
});
