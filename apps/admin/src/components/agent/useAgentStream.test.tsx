// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { Provider } from 'react-redux';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { contentApi } from '@/lib/api/contentApi';
import { store } from '@/lib/store';

import type { AgentTurn, ToolEvent } from './useAgentStream';
import { useAgentStream } from './useAgentStream';

// phase-5 task-04 (admin agent panel), RED (TDD): `useAgentStream.ts` does not exist yet — every
// import above fails to resolve (module-resolution RED, the same accepted failure mode
// `apps/client/src/components/chat/useChatStream.test.ts` documents for its own hook).
//
// Brief: docs/plans/phase-5-mcp-agent/task-04-admin-agent-panel.md, Interfaces + Step 1.
// Spec: advisordesk-prd.md §5.4 (stateless `POST /agent/chat`, SSE events `token`/`tool_call`/
// `tool_result`/`done`/`error`, client resends full history), §6 (8-tool-call cap + cap-report).
// Wire contract verified against apps/api/app/routes/agent_routes.py (`_to_sse_event` — event
// names/payloads) and apps/api/app/models/schemas/agent.py (`AgentChatRequest`: exactly
// `{messages: [{role, content}]}`). Pattern lifted from
// `apps/client/src/components/chat/useChatStream.ts`/`useChatStream.test.ts` (phase-4 t05,
// read-only reference) per the brief's Context section.
//
// Judgment calls (test-author, flagged for controller review):
// (1) `ToolEvent.detail` for a `'call'` kind is `JSON.stringify(arguments)` — the controller pin
//     "pretty-compact JSON of arguments" is read as single-line/compact `JSON.stringify` (not
//     multi-line indented `JSON.stringify(v, null, 2)`), since "compact" and multi-line pretty-
//     printing are in tension; every fixture below builds the expected `detail` string from the
//     SAME arguments object literal it feeds into the `tool_call` SSE frame, so this pin does not
//     depend on guessing the implementer's exact `JSON.stringify` call shape beyond "compact".
// (2) The store used to assert the `done`-triggered invalidation dispatch is the REAL app
//     singleton (`@/lib/store`), wrapped via a bare `<Provider store={store}>` (not the full
//     `Providers` — no MUI/theme needed for a hook-only test) — mirrors
//     `contentApi.test.ts`/`contentApiEditor.test.ts`'s own use of the real singleton store
//     rather than a fresh per-test store, and lets `vi.spyOn(store, 'dispatch')` observe the
//     hook's real dispatched action.
// (3) The exact outgoing fetch base URL is not asserted (only that the path includes
//     `/api/v1/agent/chat`) — same rationale as `useChatStream.test.ts` judgment call 3: the
//     admin app's `NEXT_PUBLIC_API_URL` resolution is an implementer decision this test doesn't
//     pin. `credentials: 'include'` IS asserted — the brief states the endpoint is
//     "admin-cookie-gated", so sending the session cookie is a hard functional requirement, not
//     an implementation detail.
// (4) The network-level-failure test (5) asserts only that `error` becomes a truthy, non-JSON-
//     looking string — no literal fallback copy is pinned, since no shared "generic error
//     message" module exists yet for `apps/admin` (unlike `apps/client/src/lib/copy.ts`) and
//     inventing one here would wrongly force the implementer to match test-author prose instead
//     of controller-approved copy (same rationale as `useChatStream.test.ts` judgment call 4).

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

// phase-8 task-22: copied verbatim from `AgentPanel/Component.test.tsx`'s own judgment call (4)
// header comment — a mocked `fetch`/`ReadableStream` that resolves entirely via microtasks can
// race ahead of `stop()`/`reset()` being called mid-stream, so the `stop`/`reset` tests below
// hold the stream open under test control rather than racing real timing.
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

function Wrapper({ children }: { children: ReactNode }) {
  return <Provider store={store}>{children}</Provider>;
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('useAgentStream', () => {
  it('lands a token/token/tool_call/tool_result/token exchange on ONE assistant turn — text accumulates around the tool events, events preserved in stream order', async () => {
    const argumentsFixture = { title: 'Roth IRA Conversion Basics', tags: ['retirement'] };
    const resultSummary = 'Created draft d-42 (Roth IRA Conversion Basics).';
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          { event: 'token', data: { text: 'Creating ' } },
          { event: 'token', data: { text: 'the draft. ' } },
          { event: 'tool_call', data: { tool: 'create_draft', arguments: argumentsFixture } },
          {
            event: 'tool_result',
            data: { tool: 'create_draft', result_summary: resultSummary },
          },
          { event: 'token', data: { text: 'Done.' } },
          {
            event: 'done',
            data: {
              tool_calls: [
                {
                  tool: 'create_draft',
                  arguments: argumentsFixture,
                  result_summary: resultSummary,
                },
              ],
            },
          },
        ]),
      ),
    );

    const { result } = renderHook(() => useAgentStream(), { wrapper: Wrapper });
    act(() => {
      result.current.send('Draft an article on Roth IRA conversion basics and tag it retirement.');
    });
    await waitFor(() => expect(result.current.streaming).toBe(false));

    const expectedEvents: ToolEvent[] = [
      {
        kind: 'call',
        tool: 'create_draft',
        detail: JSON.stringify(argumentsFixture),
        textOffset: 20,
      },
      { kind: 'result', tool: 'create_draft', detail: resultSummary, textOffset: 20 },
    ];
    const expectedTurns: AgentTurn[] = [
      {
        role: 'user',
        text: 'Draft an article on Roth IRA conversion basics and tag it retirement.',
        events: [],
      },
      { role: 'assistant', text: 'Creating the draft. Done.', events: expectedEvents },
    ];
    expect(result.current.turns).toEqual(expectedTurns);
  });

  it("§5.4: the SECOND send() POSTs the FULL prior history — both user turns and the first turn's final assistant text", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        streamResponse([
          { event: 'token', data: { text: 'Created the draft.' } },
          { event: 'done', data: { tool_calls: [] } },
        ]),
      )
      .mockResolvedValueOnce(
        streamResponse([
          { event: 'token', data: { text: 'Published it.' } },
          { event: 'done', data: { tool_calls: [] } },
        ]),
      );
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useAgentStream(), { wrapper: Wrapper });
    act(() => {
      result.current.send('Draft an article on Roth IRA basics.');
    });
    await waitFor(() => expect(result.current.streaming).toBe(false));

    act(() => {
      result.current.send('Now publish it.');
    });
    await waitFor(() => expect(result.current.streaming).toBe(false));

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [secondUrl, secondInit] = fetchMock.mock.calls[1] as [unknown, RequestInit];
    expect(String(secondUrl)).toContain('/api/v1/agent/chat');
    expect(secondInit.method).toBe('POST');
    expect(secondInit.credentials).toBe('include');
    const body = JSON.parse(String(secondInit.body)) as {
      messages: { role: string; content: string }[];
    };
    expect(body.messages).toEqual([
      { role: 'user', content: 'Draft an article on Roth IRA basics.' },
      { role: 'assistant', content: 'Created the draft.' },
      { role: 'user', content: 'Now publish it.' },
    ]);
  });

  it('a `done` event dispatches Content/Stats/Tags invalidation to the store', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          { event: 'token', data: { text: 'You have 5 published pieces on tax planning.' } },
          { event: 'done', data: { tool_calls: [] } },
        ]),
      ),
    );
    const dispatchSpy = vi.spyOn(store, 'dispatch');

    const { result } = renderHook(() => useAgentStream(), { wrapper: Wrapper });
    act(() => {
      result.current.send('How many published pieces do we have on tax planning?');
    });
    await waitFor(() => expect(result.current.streaming).toBe(false));

    expect(dispatchSpy).toHaveBeenCalledWith(
      contentApi.util.invalidateTags(['Content', 'Stats', 'Tags']),
    );
  });

  it('an `error` event sets `error` to the envelope message and ends streaming', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          { event: 'token', data: { text: 'Working on it...' } },
          {
            event: 'error',
            data: {
              error: {
                code: 'agent_stream_failed',
                message: 'The agent failed to complete this request. Please try again.',
              },
            },
          },
        ]),
      ),
    );

    const { result } = renderHook(() => useAgentStream(), { wrapper: Wrapper });
    act(() => {
      result.current.send('Do something that fails.');
    });
    await waitFor(() => expect(result.current.streaming).toBe(false));

    expect(result.current.error).toBe(
      'The agent failed to complete this request. Please try again.',
    );
  });

  it('a network-level fetch rejection surfaces a friendly error and never throws or rejects unhandled', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')));

    const { result } = renderHook(() => useAgentStream(), { wrapper: Wrapper });

    expect(() => {
      act(() => {
        result.current.send('A question.');
      });
    }).not.toThrow();

    await waitFor(() => expect(result.current.streaming).toBe(false));

    expect(result.current.error).toBeTruthy();
    // Never the raw error/JSON dumped verbatim — a friendly message.
    expect(result.current.error).not.toMatch(/[{}]/);
  });

  it('stop() aborts the in-flight stream, keeps the partial turn, sets no error, and ends streaming', async () => {
    const { response, release } = gatedStreamResponse([
      { event: 'token', data: { text: 'Partial ' } },
      { event: 'done', data: { tool_calls: [] } },
    ]);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));

    const { result } = renderHook(() => useAgentStream(), { wrapper: Wrapper });
    act(() => result.current.send('Q'));
    await waitFor(() => expect(result.current.streaming).toBe(true));

    act(() => result.current.stop());
    release();

    await waitFor(() => expect(result.current.streaming).toBe(false));
    expect(result.current.error).toBeNull();
    // p8 final, F12: pins the post-abort guard — frames released AFTER stop() must not append an
    // assistant turn; only the user's own turn survives.
    expect(result.current.turns).toHaveLength(1);
    expect(result.current.turns[0]).toEqual({ role: 'user', text: 'Q', events: [] });
  });

  it('stop() is a no-op when idle', () => {
    const { result } = renderHook(() => useAgentStream(), { wrapper: Wrapper });

    expect(() => act(() => result.current.stop())).not.toThrow();
    expect(result.current.streaming).toBe(false);
  });

  it('reset() clears turns and error, and the next send() resends an empty history', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        streamResponse([
          { event: 'token', data: { text: 'Hi' } },
          { event: 'done', data: { tool_calls: [] } },
        ]),
      )
      .mockResolvedValueOnce(
        streamResponse([
          { event: 'token', data: { text: 'Again' } },
          { event: 'done', data: { tool_calls: [] } },
        ]),
      );
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useAgentStream(), { wrapper: Wrapper });
    act(() => result.current.send('First'));
    await waitFor(() => expect(result.current.streaming).toBe(false));
    expect(result.current.turns).toHaveLength(2);

    act(() => result.current.reset());
    expect(result.current.turns).toEqual([]);
    expect(result.current.error).toBeNull();

    act(() => result.current.send('Second'));
    await waitFor(() => expect(result.current.streaming).toBe(false));
    const body = JSON.parse((fetchMock.mock.calls[1]?.[1] as RequestInit).body as string) as {
      messages: unknown[];
    };
    expect(body.messages).toEqual([{ role: 'user', content: 'Second' }]);
  });

  it('reset() while streaming aborts first and leaves no turns behind', async () => {
    const { response, release } = gatedStreamResponse([
      { event: 'token', data: { text: 'Partial ' } },
      { event: 'done', data: { tool_calls: [] } },
    ]);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));

    const { result } = renderHook(() => useAgentStream(), { wrapper: Wrapper });
    act(() => result.current.send('Q'));
    await waitFor(() => expect(result.current.streaming).toBe(true));

    act(() => result.current.reset());
    release();

    await waitFor(() => expect(result.current.streaming).toBe(false));
    expect(result.current.turns).toEqual([]);
    expect(result.current.error).toBeNull();
  });
});
