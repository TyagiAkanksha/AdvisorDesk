// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useChatStream } from './useChatStream';

// phase-9 task-17: the `done` event's `message_id` was typed and thrown away
// (`useChatStream.ts:481`). It is the capability the feedback endpoint needs, so it now lands on
// the assistant message.

function streamResponse(frames: { event: string; data: unknown }[]): Response {
  const body = frames
    .map((frame) => `event: ${frame.event}\ndata: ${JSON.stringify(frame.data)}\n\n`)
    .join('');
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(body));
        controller.close();
      },
    }),
    { status: 200, headers: { 'content-type': 'text/event-stream' } },
  );
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe('useChatStream message ids', () => {
  it('keeps the done event message_id on the assistant turn it belongs to', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          { event: 'token', data: { text: 'RSUs vest on a schedule.' } },
          {
            event: 'citations',
            data: { citations: [{ content_id: 'c-1', title: 'T', slug: 't' }] },
          },
          { event: 'done', data: { session_id: 's-1', message_id: 'm-42' } },
        ]),
      ),
    );

    const { result } = renderHook(() => useChatStream());
    act(() => result.current.send('When do my RSUs vest?'));

    await waitFor(() => expect(result.current.streaming).toBe(false));

    expect(result.current.messages[0]?.role).toBe('user');
    expect(result.current.messages[0]?.messageId).toBeUndefined();
    expect(result.current.messages[1]?.role).toBe('assistant');
    expect(result.current.messages[1]?.messageId).toBe('m-42');
    expect(localStorage.getItem('advisordesk_session')).toBe('s-1');
  });

  it('leaves earlier turns alone when a second answer arrives', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(
          streamResponse([
            { event: 'token', data: { text: 'First.' } },
            { event: 'done', data: { session_id: 's-1', message_id: 'm-1' } },
          ]),
        )
        .mockResolvedValueOnce(
          streamResponse([
            { event: 'token', data: { text: 'Second.' } },
            { event: 'done', data: { session_id: 's-1', message_id: 'm-2' } },
          ]),
        ),
    );

    const { result } = renderHook(() => useChatStream());
    act(() => result.current.send('one'));
    await waitFor(() => expect(result.current.streaming).toBe(false));
    act(() => result.current.send('two'));
    await waitFor(() => expect(result.current.streaming).toBe(false));

    expect(result.current.messages.map((message) => message.messageId)).toEqual([
      undefined,
      'm-1',
      undefined,
      'm-2',
    ]);
  });
});
