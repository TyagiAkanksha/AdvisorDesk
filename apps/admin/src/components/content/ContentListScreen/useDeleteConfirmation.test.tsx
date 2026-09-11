// @vitest-environment jsdom
import { act, renderHook, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import { navigation } from '@/testing/nextNavigation';
import type { ContentDto, ContentListDto } from '@/types/api/content';

import { useContentList } from './useContentList';
import { useDeleteConfirmation } from './useDeleteConfirmation';

vi.mock('next/navigation', () => import('@/testing/nextNavigation'));

// hygiene t06 M6: the delete-confirmation state that used to live in this screen's
// Component.tsx (which row is pending deletion, open/close, confirm -> mutation -> snackbar)
// moves into this colocated hook. RED today: the module does not exist.
function Wrapper({ children }: { children: ReactNode }) {
  return <Providers>{children}</Providers>;
}

function useHarness() {
  const list = useContentList();
  const confirmation = useDeleteConfirmation({
    deleteContent: list.deleteContent,
    clearDeleteError: list.clearDeleteError,
  });
  return { list, confirmation };
}

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

const itemB: ContentDto = {
  ...itemA,
  id: '22222222-2222-2222-2222-222222222222',
  slug: 'estate-planning-101',
  title: 'Estate Planning 101',
};

const listFixture: ContentListDto = { items: [itemA, itemB], page: 1, page_size: 20, total: 2 };

const DELETE_FAILURE_MESSAGE = 'Could not delete due to a database hiccup.';
const deleteOk = () => new Response(null, { status: 204 });
const deleteFails = () =>
  jsonResponse({ error: { code: 'internal_error', message: DELETE_FAILURE_MESSAGE } }, 500);

function mockFetch(deleteResponse: (attempt: number) => Response) {
  let attempts = 0;
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
    async (input, init) => {
      const pathname = pathnameOf(input);
      const method = requestMethod(input, init);

      if (pathname === '/api/v1/content' && method === 'GET') {
        return jsonResponse(listFixture);
      }
      if (pathname.startsWith('/api/v1/content/') && method === 'DELETE') {
        attempts += 1;
        return deleteResponse(attempts);
      }
      return jsonResponse({ error: { code: 'not_found', message: 'unmocked route' } }, 404);
    },
  );
  global.fetch = fetchMock;
  return fetchMock;
}

describe('useDeleteConfirmation', () => {
  beforeEach(() => {
    navigation.reset('/content');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('open(item) arms the dialog for that row and close() disarms it', async () => {
    mockFetch(deleteOk);
    const { result } = renderHook(() => useHarness(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.list.hasData).toBe(true));

    expect(result.current.confirmation.isOpen).toBe(false);
    expect(result.current.confirmation.target).toBeNull();

    act(() => result.current.confirmation.open(itemB));
    expect(result.current.confirmation.isOpen).toBe(true);
    expect(result.current.confirmation.target).toEqual(itemB);

    act(() => result.current.confirmation.close());
    expect(result.current.confirmation.isOpen).toBe(false);
    expect(result.current.confirmation.target).toBeNull();
  });

  it('confirm() deletes the armed row, disarms the dialog and reports through the snackbar', async () => {
    const fetchMock = mockFetch(deleteOk);
    const { result } = renderHook(() => useHarness(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.list.hasData).toBe(true));

    act(() => result.current.confirmation.open(itemA));
    await act(async () => {
      await result.current.confirmation.confirm();
    });

    const deleteCall = fetchMock.mock.calls.find(
      ([input, init]) => requestMethod(input, init) === 'DELETE',
    );
    expect(deleteCall).toBeDefined();
    expect(pathnameOf(deleteCall![0])).toBe(`/api/v1/content/${itemA.id}`);
    expect(result.current.confirmation.isOpen).toBe(false);
    // The skeleton also uses role="status" on this screen — query the notice by its text.
    expect(await screen.findByText('Deleted')).toBeInTheDocument();
  });

  it('a failed confirm() keeps the row armed and leaves the message on the list hook', async () => {
    mockFetch(deleteFails);
    const { result } = renderHook(() => useHarness(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.list.hasData).toBe(true));

    act(() => result.current.confirmation.open(itemA));
    await act(async () => {
      await result.current.confirmation.confirm();
    });

    expect(result.current.confirmation.isOpen).toBe(true);
    expect(result.current.confirmation.target).toEqual(itemA);
    expect(result.current.list.deleteError).toBe(DELETE_FAILURE_MESSAGE);
  });

  it('arming another row clears the previous failure message', async () => {
    mockFetch((attempt) => (attempt === 1 ? deleteFails() : deleteOk()));
    const { result } = renderHook(() => useHarness(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.list.hasData).toBe(true));

    act(() => result.current.confirmation.open(itemA));
    await act(async () => {
      await result.current.confirmation.confirm();
    });
    expect(result.current.list.deleteError).toBe(DELETE_FAILURE_MESSAGE);

    act(() => result.current.confirmation.open(itemB));

    expect(result.current.list.deleteError).toBeNull();
    expect(result.current.confirmation.target).toEqual(itemB);
  });

  it('confirm() with no armed row resolves without touching the API', async () => {
    const fetchMock = mockFetch(deleteOk);
    const { result } = renderHook(() => useHarness(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.list.hasData).toBe(true));

    await act(async () => {
      await result.current.confirmation.confirm();
    });

    expect(
      fetchMock.mock.calls.some(([input, init]) => requestMethod(input, init) === 'DELETE'),
    ).toBe(false);
  });
});
