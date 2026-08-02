// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { Provider } from 'react-redux';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { contentApi } from '@/lib/api/contentApi';
import { store } from '@/lib/store';

import { useAgentStream } from './useAgentStream';

// phase-5 task-04 review round 1 (`.superpowers/sdd/reports/p5-t04-review.md`), finding I-1 —
// implementer-authored fix-round test (not test-author-pinned; per the coordinator's fix-round
// dispatch, new behavior gets a new file, e.g. this one, rather than edits to the pinned
// `useAgentStream.test.tsx`).
//
// I-1: a `done` event arriving with ZERO preceding `token`/`tool_call` events on that turn left
// NO assistant turn in state — the user sees their own bubble and silence. Reachable against the
// real API: `app/agent/llm.py`'s adapter yields `Done([])` for a completion with neither content
// nor tool calls, so `onDone` fired with no `onToken`/`onToolCall` ever having run first. Mirrors
// the client precedent the phase-4 review hardened on
// (`apps/client/src/components/chat/useChatStream.ts`'s M-7: a `citations` event with no
// preceding token still starts an empty assistant turn rather than dropping the response).
//
// Local helpers only — deliberately NOT imported from the pinned `useAgentStream.test.tsx` (this
// file must stand on its own and never risk coupling to, or drifting from, a pinned fixture).

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
  return new Response(body, {
    status: 200,
    headers: { 'content-type': 'text/event-stream' },
  });
}

function Wrapper({ children }: { children: ReactNode }) {
  return <Provider store={store}>{children}</Provider>;
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('useAgentStream — I-1 empty-done fallback turn', () => {
  it('a `done` with no preceding token/tool_call events still yields an assistant turn with honest fallback text, and no error state', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(streamResponse([{ event: 'done', data: { tool_calls: [] } }])),
    );

    const { result } = renderHook(() => useAgentStream(), { wrapper: Wrapper });
    act(() => {
      result.current.send('Do something the agent has nothing to say about.');
    });
    await waitFor(() => expect(result.current.streaming).toBe(false));

    expect(result.current.turns).toEqual([
      {
        role: 'user',
        text: 'Do something the agent has nothing to say about.',
        events: [],
      },
      {
        role: 'assistant',
        text: 'The agent returned no response. Please try again.',
        events: [],
      },
    ]);
    // Streaming ended cleanly, not via the error path.
    expect(result.current.error).toBeNull();
  });

  it('still dispatches Content/Stats/Tags invalidation on an empty `done`, exactly as a non-empty one does', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(streamResponse([{ event: 'done', data: { tool_calls: [] } }])),
    );
    const dispatchSpy = vi.spyOn(store, 'dispatch');

    const { result } = renderHook(() => useAgentStream(), { wrapper: Wrapper });
    act(() => {
      result.current.send('Another empty completion.');
    });
    await waitFor(() => expect(result.current.streaming).toBe(false));

    expect(dispatchSpy).toHaveBeenCalledWith(
      contentApi.util.invalidateTags(['Content', 'Stats', 'Tags']),
    );
  });

  it('does NOT append a second, redundant assistant turn when tool events (but no tokens) already produced one', async () => {
    const argumentsFixture = { title: 'Untitled' };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          { event: 'tool_call', data: { tool: 'create_draft', arguments: argumentsFixture } },
          {
            event: 'tool_result',
            data: { tool: 'create_draft', result_summary: 'Created draft d-1 (Untitled).' },
          },
          { event: 'done', data: { tool_calls: [] } },
        ]),
      ),
    );

    const { result } = renderHook(() => useAgentStream(), { wrapper: Wrapper });
    act(() => {
      result.current.send('Draft something.');
    });
    await waitFor(() => expect(result.current.streaming).toBe(false));

    // Exactly two turns: the user turn, and ONE assistant turn carrying the tool events — no
    // extra fallback turn tacked on just because `text` happens to be empty.
    expect(result.current.turns).toHaveLength(2);
    expect(result.current.turns[1].role).toBe('assistant');
    expect(result.current.turns[1].events).toHaveLength(2);
  });
});
