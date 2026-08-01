// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatMessage } from './useChatStream';
import { useChatStream } from './useChatStream';

// task-05 review round 1 (`.superpowers/sdd/reports/p4-t05-review.md`) — implementer-authored
// (not test-author-pinned; new behavior gets new test files per the coordinator's fix-round
// dispatch). Covers `useChatStream`'s hook-level hardening: I-3 (a throwing `localStorage`
// accessor must not block `send()` before `fetch`, nor turn a successful answer into an error
// banner), M-4 (`send()` re-entrancy guard), M-5 (`AbortController` wired to unmount), and the
// hook half of M-7 (a `citations` event with no preceding `token` must still render an assistant
// turn, not a silent blank).
//
// Local helpers only — deliberately NOT imported from the pinned `useChatStream.test.ts`.

interface SseFrame {
  event: string;
  data: unknown;
}

function sseBody(frames: SseFrame[]): string {
  return frames
    .map((frame) => `event: ${frame.event}\ndata: ${JSON.stringify(frame.data)}\n\n`)
    .join('');
}

function streamResponse(frames: SseFrame[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(sseBody(frames)));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { 'content-type': 'text/event-stream' } });
}

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

/** A `Response` whose SSE body stays open until `release()` is called — used to hold `send()`'s
 * exchange open long enough to observe re-entrancy / abort behavior deterministically, instead
 * of racing a fully-microtask-resolving stream (mirrors the pinned `ChatScreen/Component.test.tsx`'s
 * `gatedStreamResponse`, independently reimplemented here). */
function gatedStreamResponse(frames: SseFrame[]): { response: Response; release: () => void } {
  const gate = deferred<void>();
  const body = new ReadableStream<Uint8Array>({
    async start(controller) {
      await gate.promise;
      controller.enqueue(new TextEncoder().encode(sseBody(frames)));
      controller.close();
    },
  });
  const response = new Response(body, {
    status: 200,
    headers: { 'content-type': 'text/event-stream' },
  });
  return { response, release: () => gate.resolve() };
}

/** Never resolves — used only to hold `fetch` itself open (distinct from `gatedStreamResponse`,
 * which holds the STREAM BODY open after a resolved response) so a test can inspect the request
 * `init` (e.g. its `AbortSignal`) before anything downstream ever runs. */
function pendingForever(): Promise<Response> {
  return new Promise(() => {});
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe('useChatStream — I-3 localStorage failure tolerance', () => {
  it('a throwing GETTER does not block send() before fetch is issued, and does not surface an error', async () => {
    vi.stubGlobal('localStorage', {
      getItem: () => {
        throw new DOMException('blocked', 'SecurityError');
      },
      setItem: () => {},
    });
    const fetchMock = vi.fn().mockResolvedValue(
      streamResponse([
        { event: 'token', data: { text: 'Answer.' } },
        { event: 'citations', data: { citations: [] } },
        { event: 'done', data: { session_id: 's', message_id: 'm' } },
      ]),
    );
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useChatStream());
    act(() => {
      result.current.send('A question.');
    });

    await waitFor(() => expect(result.current.streaming).toBe(false));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.current.error).toBeNull();
  });

  it('a throwing setItem does not turn a successful answer into an error banner', async () => {
    vi.stubGlobal('localStorage', {
      getItem: () => null,
      setItem: () => {
        throw new DOMException('quota', 'QuotaExceededError');
      },
    });
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          { event: 'token', data: { text: 'Answer.' } },
          { event: 'citations', data: { citations: [] } },
          { event: 'done', data: { session_id: 's', message_id: 'm' } },
        ]),
      ),
    );

    const { result } = renderHook(() => useChatStream());
    act(() => {
      result.current.send('A question.');
    });

    await waitFor(() => expect(result.current.streaming).toBe(false));

    expect(result.current.error).toBeNull();
    const assistant = result.current.messages.find(
      (message: ChatMessage) => message.role === 'assistant',
    );
    expect(assistant?.text).toBe('Answer.');
  });
});

describe('useChatStream — M-4 re-entrancy guard', () => {
  it('send() is a no-op while a stream is already in flight', async () => {
    const { response, release } = gatedStreamResponse([
      { event: 'token', data: { text: 'Answer.' } },
      { event: 'citations', data: { citations: [] } },
      { event: 'done', data: { session_id: 's', message_id: 'm' } },
    ]);
    const fetchMock = vi.fn().mockResolvedValue(response);
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useChatStream());
    act(() => {
      result.current.send('first question');
    });
    act(() => {
      result.current.send('second question');
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(
      result.current.messages.filter((message: ChatMessage) => message.role === 'user'),
    ).toHaveLength(1);

    release();
    await waitFor(() => expect(result.current.streaming).toBe(false));
  });
});

describe('useChatStream — M-5 AbortController wired to unmount', () => {
  it('passes an AbortSignal to fetch, and aborts it when the component unmounts', async () => {
    const fetchMock = vi.fn().mockReturnValue(pendingForever());
    vi.stubGlobal('fetch', fetchMock);

    const { result, unmount } = renderHook(() => useChatStream());
    act(() => {
      result.current.send('A question.');
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.signal).toBeInstanceOf(AbortSignal);
    expect(init.signal?.aborted).toBe(false);

    unmount();

    expect(init.signal?.aborted).toBe(true);
  });
});

describe('useChatStream — M-7 hook half: citations with no preceding token', () => {
  it('a citations event with no preceding token still renders an assistant turn, not a silent blank', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          { event: 'citations', data: { citations: [] } },
          { event: 'done', data: { session_id: 's', message_id: 'm' } },
        ]),
      ),
    );

    const { result } = renderHook(() => useChatStream());
    act(() => {
      result.current.send('A question.');
    });

    await waitFor(() => expect(result.current.streaming).toBe(false));

    const assistant = result.current.messages.find(
      (message: ChatMessage) => message.role === 'assistant',
    );
    expect(assistant).toBeDefined();
    expect(assistant?.citations).toEqual([]);
    expect(assistant?.refusal).toBe(true);
  });
});
