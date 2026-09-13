// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { GENERIC_ERROR_MESSAGE } from '@/lib/copy';

import { useMessageFeedback } from './useMessageFeedback';

// Only the network edge is mocked (docs/FRONTEND-CONVENTIONS.md §7) — the hook's own state machine
// is exercised for real.

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
} {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('useMessageFeedback', () => {
  it('shows nothing rated and nothing pending before any click', () => {
    const { result } = renderHook(() => useMessageFeedback());

    expect(result.current.valueFor('m-1')).toBeNull();
    expect(result.current.pendingFor('m-1')).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('applies the rating optimistically and POSTs it once', async () => {
    const gate = deferred<Response>();
    const fetchMock = vi.fn().mockReturnValue(gate.promise);
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useMessageFeedback());
    act(() => result.current.select('m-1', 1));

    expect(result.current.valueFor('m-1')).toBe(1);
    expect(result.current.pendingFor('m-1')).toBe(true);

    await act(async () => {
      gate.resolve(new Response(null, { status: 204 }));
      await gate.promise;
    });

    await waitFor(() => expect(result.current.pendingFor('m-1')).toBe(false));
    expect(result.current.valueFor('m-1')).toBe(1);
    expect(result.current.error).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('reverts to the previous rating and shows friendly copy when the request fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(new Response(null, { status: 204 }))
        .mockResolvedValueOnce(new Response('{}', { status: 404 })),
    );

    const { result } = renderHook(() => useMessageFeedback());

    act(() => result.current.select('m-1', 1));
    await waitFor(() => expect(result.current.pendingFor('m-1')).toBe(false));
    expect(result.current.valueFor('m-1')).toBe(1);

    act(() => result.current.select('m-1', -1));
    await waitFor(() => expect(result.current.pendingFor('m-1')).toBe(false));

    // Reverted to the value it had BEFORE the failed click — not to null.
    expect(result.current.valueFor('m-1')).toBe(1);
    expect(result.current.error).toBe(GENERIC_ERROR_MESSAGE);
  });

  it('clears a stale error once a later rating succeeds', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(new Response('{}', { status: 500 }))
        .mockResolvedValueOnce(new Response(null, { status: 204 })),
    );

    const { result } = renderHook(() => useMessageFeedback());

    act(() => result.current.select('m-1', -1));
    await waitFor(() => expect(result.current.error).toBe(GENERIC_ERROR_MESSAGE));

    act(() => result.current.select('m-2', 1));
    await waitFor(() => expect(result.current.error).toBeNull());
    expect(result.current.valueFor('m-2')).toBe(1);
  });

  it('keeps each message independent and ignores a second click while one is in flight', async () => {
    const gate = deferred<Response>();
    const fetchMock = vi.fn().mockReturnValue(gate.promise);
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useMessageFeedback());

    act(() => result.current.select('m-1', 1));
    act(() => result.current.select('m-1', -1));

    expect(result.current.valueFor('m-1')).toBe(1);
    expect(result.current.valueFor('m-2')).toBeNull();
    expect(result.current.pendingFor('m-2')).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      gate.resolve(new Response(null, { status: 204 }));
      await gate.promise;
    });
  });
});
