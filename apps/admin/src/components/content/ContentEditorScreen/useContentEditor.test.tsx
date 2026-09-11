// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';

import { useContentEditor } from './useContentEditor';
import {
  draftFixture,
  editHandler,
  mockEditorFetchWith as mockFetch,
  requestBody,
  requestMethod,
} from './testing/renderEditor';

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

  // hygiene t07 (phase-8 t19 M3): the trimmed-title rule must also keep the unload guard
  // disarmed — a blank-looking form is not unsaved work.
  it('new mode: a whitespace-only title does not arm the beforeunload guard', () => {
    mockFetch(editHandler);
    const { result } = renderHook(() => useContentEditor({}), { wrapper: Wrapper });

    act(() => result.current.setTitle('   '));

    const event = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
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
