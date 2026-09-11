// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import { navigation } from '@/testing/nextNavigation';
import type { ContentListDto } from '@/types/api/content';

import { useContentList } from './useContentList';

vi.mock('next/navigation', () => import('@/testing/nextNavigation'));

function Wrapper({ children }: { children: ReactNode }) {
  return <Providers>{children}</Providers>;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function requestUrl(input: RequestInfo | URL): string {
  return input instanceof Request ? input.url : String(input);
}

const emptyPage = (total: number, page: number): ContentListDto => ({
  items: [],
  page,
  page_size: 20,
  total,
});

function mockList(handler: (url: URL) => ContentListDto) {
  const fetchMock = vi.fn<(input: RequestInfo | URL) => Promise<Response>>(async (input) => {
    const url = new URL(requestUrl(input));
    if (url.pathname === '/api/v1/content') return jsonResponse(handler(url));
    return jsonResponse({ error: { code: 'not_found', message: 'unmocked' } }, 404);
  });
  global.fetch = fetchMock;
  return fetchMock;
}

describe('useContentList — URL is the filter state', () => {
  beforeEach(() => {
    navigation.reset('/content');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('reads status/tag/q/page from the URL', () => {
    navigation.reset('/content?status=draft&tag=retirement&q=roth&page=3');
    mockList(() => emptyPage(100, 3));

    const { result } = renderHook(() => useContentList(), { wrapper: Wrapper });

    expect(result.current.status).toBe('draft');
    expect(result.current.tag).toBe('retirement');
    expect(result.current.q).toBe('roth');
    expect(result.current.page).toBe(3);
    expect(result.current.hasFilters).toBe(true);
  });

  it('setStatus writes the URL with the page reset', async () => {
    // total 40 → page 2 is valid, so the clamp effect stays out of this test's way.
    mockList((url) => emptyPage(40, Number(url.searchParams.get('page') ?? 1)));
    navigation.reset('/content?page=2');
    const { result } = renderHook(() => useContentList(), { wrapper: Wrapper });

    act(() => result.current.setStatus('published'));

    expect(navigation.replace).toHaveBeenLastCalledWith('/content?status=published', {
      scroll: false,
    });
    await waitFor(() => expect(result.current.status).toBe('published'));
    expect(result.current.page).toBe(1);
  });

  it('setQ updates the field immediately and writes the URL after the debounce', async () => {
    mockList(() => emptyPage(0, 1));
    const { result } = renderHook(() => useContentList(), { wrapper: Wrapper });

    act(() => result.current.setQ('ro'));
    expect(result.current.q).toBe('ro');
    expect(navigation.replace).not.toHaveBeenCalled();
    act(() => result.current.setQ('roth'));

    await waitFor(
      () =>
        expect(navigation.replace).toHaveBeenLastCalledWith('/content?q=roth', { scroll: false }),
      { timeout: 2000 },
    );
    expect(navigation.replace).toHaveBeenCalledTimes(1);
  });

  it('a status change inside the debounce window is not reverted by the pending q write (review I-1)', async () => {
    mockList(() => emptyPage(0, 1));
    const { result } = renderHook(() => useContentList(), { wrapper: Wrapper });

    act(() => result.current.setQ('roth'));
    act(() => result.current.setStatus('published'));
    expect(navigation.replace).toHaveBeenLastCalledWith('/content?status=published', {
      scroll: false,
    });

    await waitFor(
      () =>
        expect(navigation.replace).toHaveBeenLastCalledWith('/content?status=published&q=roth', {
          scroll: false,
        }),
      { timeout: 2000 },
    );
    expect(navigation.replace).toHaveBeenCalledTimes(2);
  });

  it('an external URL change (back button) updates the search field', async () => {
    mockList(() => emptyPage(0, 1));
    navigation.reset('/content?q=roth');
    const { result } = renderHook(() => useContentList(), { wrapper: Wrapper });
    expect(result.current.q).toBe('roth');

    act(() => navigation.reset('/content'));

    await waitFor(() => expect(result.current.q).toBe(''));
  });

  it('clearFilters writes /content and empties the field', async () => {
    mockList(() => emptyPage(0, 1));
    navigation.reset('/content?status=draft&q=roth');
    const { result } = renderHook(() => useContentList(), { wrapper: Wrapper });

    act(() => result.current.clearFilters());

    expect(navigation.replace).toHaveBeenLastCalledWith('/content', { scroll: false });
    await waitFor(() => expect(result.current.hasFilters).toBe(false));
    expect(result.current.q).toBe('');
  });

  it('clamps a stranded page to the last page once the total is known (WR-60)', async () => {
    navigation.reset('/content?page=5');
    mockList((url) => emptyPage(25, Number(url.searchParams.get('page') ?? 1)));

    renderHook(() => useContentList(), { wrapper: Wrapper });

    await waitFor(() =>
      expect(navigation.replace).toHaveBeenLastCalledWith('/content?page=2', { scroll: false }),
    );
  });

  it('never clamps below page 1 or when the page is valid', async () => {
    navigation.reset('/content?page=2');
    mockList(() => emptyPage(25, 2));

    const { result } = renderHook(() => useContentList(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.hasData).toBe(true));
    expect(navigation.replace).not.toHaveBeenCalled();
  });
});
