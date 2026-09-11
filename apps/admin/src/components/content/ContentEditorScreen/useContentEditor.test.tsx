// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';
import type { ContentDto } from '@/types/api/content';

import { useContentEditor } from './useContentEditor';

// Task 19 (C5, hook half): `useContentEditor` gains required-title validation, an `isDirty`
// flag that also drives a `beforeunload` guard, tag suggestions from `GET /tags`, and the
// loaded record's header fields — and loses its private snackbar (feedback now goes through
// the global `useSnackbar()`, exercised at the screen level in feedback.test.tsx). RED today:
// none of `titleError`/`onTitleBlur`/`isDirty`/`savedTitle`/`slug`/`status`/`createdAt`/
// `updatedAt`/`publishedAt`/`tagOptions` exist on the hook's result yet, and the hook still
// exposes `snackbarMessage`/`closeSnackbar`.
const pushMock = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn() }),
}));

function Wrapper({ children }: { children: ReactNode }) {
  return <Providers>{children}</Providers>;
}

function requestUrl(input: RequestInfo | URL): string {
  return input instanceof Request ? input.url : String(input);
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  return input instanceof Request ? input.method : (init?.method ?? 'GET');
}

async function requestBody(input: RequestInfo | URL, init?: RequestInit): Promise<unknown> {
  if (input instanceof Request) return input.clone().json();
  return JSON.parse(String(init?.body));
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

// test-author simplification (brief note, task-19): the extra `input`/`init` args of the
// original 4-arg `Handler` shape are unused by every handler body below — trimmed to
// `(url, method) => Response` and kept consistent with feedback.test.tsx.
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

describe('useContentEditor', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    pushMock.mockClear();
  });

  it('new mode: titleError appears after blurring a blank title and clears once typed', () => {
    mockFetch(editHandler);
    const { result } = renderHook(() => useContentEditor({}), { wrapper: Wrapper });

    expect(result.current.titleError).toBeNull();
    act(() => result.current.onTitleBlur());
    expect(result.current.titleError).toBe('Title is required');

    act(() => result.current.setTitle('A title'));
    expect(result.current.titleError).toBeNull();
  });

  it('new mode: onSubmit with a blank title sets titleError and sends no request', () => {
    const fetchMock = mockFetch(editHandler);
    const { result } = renderHook(() => useContentEditor({}), { wrapper: Wrapper });

    act(() => result.current.setTitle('   '));
    act(() => result.current.onSubmit());

    expect(result.current.titleError).toBe('Title is required');
    expect(
      fetchMock.mock.calls.some(([input, init]) => requestMethod(input, init) === 'POST'),
    ).toBe(false);
  });

  it('new mode: isDirty is false on a blank form and true once any field has content', () => {
    mockFetch(editHandler);
    const { result } = renderHook(() => useContentEditor({}), { wrapper: Wrapper });

    expect(result.current.isDirty).toBe(false);
    act(() => result.current.setBody('draft text'));
    expect(result.current.isDirty).toBe(true);
    act(() => result.current.setBody(''));
    expect(result.current.isDirty).toBe(false);
  });

  // p8 final, F7: a whitespace-only title must not count as "any field has content" — it is
  // the same "blank" the required-title validation already treats it as.
  it('new mode: isDirty stays false when the title is whitespace only', () => {
    mockFetch(editHandler);
    const { result } = renderHook(() => useContentEditor({}), { wrapper: Wrapper });

    act(() => result.current.setTitle('   '));

    expect(result.current.isDirty).toBe(false);
  });

  it('installs a beforeunload guard only while dirty', () => {
    mockFetch(editHandler);
    const { result } = renderHook(() => useContentEditor({}), { wrapper: Wrapper });

    const clean = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(clean);
    expect(clean.defaultPrevented).toBe(false);

    act(() => result.current.setTitle('Unsaved'));
    const dirty = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(dirty);
    expect(dirty.defaultPrevented).toBe(true);

    act(() => result.current.setTitle(''));
    const cleanAgain = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(cleanAgain);
    expect(cleanAgain.defaultPrevented).toBe(false);
  });

  it("edit mode: exposes the record's header fields; savedTitle stays the saved value while the field changes", async () => {
    mockFetch(editHandler);
    const { result } = renderHook(() => useContentEditor({ contentId: draftFixture.id }), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.hasContent).toBe(true));
    expect(result.current.savedTitle).toBe(draftFixture.title);
    expect(result.current.slug).toBe(draftFixture.slug);
    expect(result.current.status).toBe('draft');
    expect(result.current.createdAt).toBe(draftFixture.created_at);
    expect(result.current.updatedAt).toBe(draftFixture.updated_at);
    expect(result.current.publishedAt).toBeNull();

    act(() => result.current.setTitle('Renamed'));
    expect(result.current.savedTitle).toBe(draftFixture.title);
    expect(result.current.isDirty).toBe(true);
  });

  it('edit mode: the saved title is trimmed in the PATCH body', async () => {
    const fetchMock = mockFetch(editHandler);
    const { result } = renderHook(() => useContentEditor({ contentId: draftFixture.id }), {
      wrapper: Wrapper,
    });
    await waitFor(() => expect(result.current.hasContent).toBe(true));

    act(() => result.current.setTitle('  Trimmed title  '));
    act(() => result.current.onSubmit());

    await waitFor(async () => {
      const patch = fetchMock.mock.calls.find(
        ([input, init]) => requestMethod(input, init) === 'PATCH',
      );
      expect(patch).toBeDefined();
      expect(await requestBody(patch![0], patch![1])).toEqual({ title: 'Trimmed title' });
    });
  });

  it('tagOptions come from GET /tags', async () => {
    mockFetch(editHandler);
    const { result } = renderHook(() => useContentEditor({}), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.tagOptions).toEqual(['retirement', 'tax-planning']));
  });

  it('no longer exposes a private snackbar', () => {
    mockFetch(editHandler);
    const { result } = renderHook(() => useContentEditor({}), { wrapper: Wrapper });

    expect('snackbarMessage' in result.current).toBe(false);
    expect('closeSnackbar' in result.current).toBe(false);
  });
});
