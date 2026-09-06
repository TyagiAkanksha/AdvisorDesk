// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatMessage } from './useChatStream';
import { parseSseStream, useChatStream } from './useChatStream';

// task-05 (phase-4), RED (TDD): `useChatStream.ts` does not exist yet — every import above
// fails to resolve (`ModuleNotFoundError`-equivalent at the TS/bundler level), which is the
// expected RED failure this file exists to produce (task-05 brief STOP RULE: "TS strict must
// compile EXCEPT for imports of the not-yet-existing modules").
//
// Brief: docs/plans/phase-4-rag-assistant/task-05-client-chat-ui.md, Interfaces + Step 1.
// Spec: advisordesk-prd.md §5.3 (SSE event shapes: `token {text}`, `citations {citations:[...]}`,
// `done {session_id,message_id}`, `error {error:{code,message}}`; localStorage-only sessions, no
// cookies), §9 (rate limiting / friendly error copy). Wire contract verified against
// apps/api/app/routes/sse.py (`event: <name>\ndata: <json>\n\n` framing) and
// apps/api/tests/test_public_chat.py (READ ONLY — the server's actual event bodies).
//
// Judgment calls (test-author, flagged for controller review):
// (1) `parseSseStream`/`useChatStream`/`ChatMessage` are all authored as living in this ONE
//     colocated file (`useChatStream.ts`) — the brief's Files list creates only this single hook
//     file under `src/components/chat/` (no separate `parseSseStream.ts`), and FRONTEND-
//     CONVENTIONS.md §3 ("VM hooks are flat and colocated... with their Args/Result interfaces
//     declared in-file") supports keeping the standalone parser next to the hook that is its only
//     caller today. Phase-5 "lifting" it for `useAgentStream` is a later task's concern (import
//     path move), not this task's.
// (2) `SseHandlers` shape (not pinned by the brief beyond "handlers"): `onToken(text)`,
//     `onCitations(citations)`, `onDone({session_id,message_id})`, `onError({code,message})` —
//     each handler receives the EVENT'S PAYLOAD UNWRAPPED (e.g. `onError` gets `{code,message}`,
//     not `{error:{code,message}}`; `onCitations` gets the array, not `{citations:[...]}`) since
//     that is what every caller actually wants. Locked in by the exact `toEqual` assertions below.
// (3) The exact outgoing fetch URL/base is NOT asserted (only that it targets
//     `/api/v1/public/chat`) — `apps/client/src/lib/publicApi.ts`'s server-only `API_URL` env var
//     cannot be used from this client island (Next.js only inlines `NEXT_PUBLIC_*` into the
//     browser bundle), so the exact base-URL resolution is an implementer decision this test
//     deliberately does not pin.
// (4) 429 "friendly copy" (brief: "the §9 friendly copy"): PRD §9 only says "frontends surface
//     friendly messages" — no literal string is pinned anywhere. Test 11 below asserts *properties*
//     of the message (non-empty, not raw JSON) rather than an exact string, since inventing a
//     literal string here would wrongly force the implementer to match test-author prose instead
//     of controller-approved copy.
// (5) Two tests beyond the brief's explicit Step-1 bullet list, both directly required by the
//     pinned Interfaces text rather than added scope: `streaming` transitions synchronously true
//     then false (the Result shape literally pins `streaming: boolean`), and a PRE-EXISTING
//     localStorage session is sent on the very first `send()` (Interfaces: "session_id read
//     from... localStorage" — the acceptance criterion "reload keeps the same session" requires
//     this read-on-first-use behavior, not just the persist-on-`done` half).

// ---------------------------------------------------------------------------
// SSE fixture helpers (local to this file; small enough not to warrant a shared non-test module,
// which the test-author brief's STOP RULE forbids creating anyway).
// ---------------------------------------------------------------------------

interface SseFrame {
  event: string;
  data: unknown;
}

function sseBody(frames: SseFrame[]): string {
  return frames
    .map((frame) => `event: ${frame.event}\ndata: ${JSON.stringify(frame.data)}\n\n`)
    .join('');
}

function readerForChunks(chunks: string[]): ReadableStreamDefaultReader<Uint8Array> {
  const encoded = chunks.map((chunk) => new TextEncoder().encode(chunk));
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of encoded) {
        controller.enqueue(chunk);
      }
      controller.close();
    },
  });
  return stream.getReader();
}

function readerFor(body: string): ReadableStreamDefaultReader<Uint8Array> {
  return readerForChunks([body]);
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

function jsonErrorResponse(status: number, code: string, message: string): Response {
  return new Response(JSON.stringify({ error: { code, message } }), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

interface RecordedEvent {
  kind: 'token' | 'citations' | 'done' | 'error';
  payload: unknown;
}

function recordingHandlers(): {
  calls: RecordedEvent[];
  onToken: (text: string) => void;
  onCitations: (citations: unknown) => void;
  onDone: (payload: unknown) => void;
  onError: (payload: unknown) => void;
} {
  const calls: RecordedEvent[] = [];
  return {
    calls,
    onToken: (text) => calls.push({ kind: 'token', payload: text }),
    onCitations: (citations) => calls.push({ kind: 'citations', payload: citations }),
    onDone: (payload) => calls.push({ kind: 'done', payload }),
    onError: (payload) => calls.push({ kind: 'error', payload }),
  };
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
});

// ---------------------------------------------------------------------------
// parseSseStream — standalone parser (liftable for phase-5's useAgentStream).
// ---------------------------------------------------------------------------

describe('parseSseStream', () => {
  it('parses token, citations, and done events in order, calling the matching handler for each', async () => {
    const reader = readerFor(
      sseBody([
        { event: 'token', data: { text: 'Hello ' } },
        { event: 'token', data: { text: 'world.' } },
        {
          event: 'citations',
          data: { citations: [{ content_id: 'c-1', title: 'T', slug: 't' }] },
        },
        { event: 'done', data: { session_id: 's-1', message_id: 'm-1' } },
      ]),
    );
    const { calls, onToken, onCitations, onDone, onError } = recordingHandlers();

    await parseSseStream(reader, { onToken, onCitations, onDone, onError });

    expect(calls).toEqual([
      { kind: 'token', payload: 'Hello ' },
      { kind: 'token', payload: 'world.' },
      { kind: 'citations', payload: [{ content_id: 'c-1', title: 'T', slug: 't' }] },
      { kind: 'done', payload: { session_id: 's-1', message_id: 'm-1' } },
    ]);
  });

  it('parses a frame whose bytes are split across two reader.read() chunks, mid-event', async () => {
    // The load-bearing case for real networks: a chunk boundary falls INSIDE the `data:` line's
    // JSON payload, not conveniently on a frame ("\n\n") boundary.
    const full = 'event: token\ndata: {"text":"hello world"}\n\n';
    const splitAt = full.indexOf('"hello') + 3;
    const chunk1 = full.slice(0, splitAt);
    const chunk2 = full.slice(splitAt);
    expect(chunk1.length).toBeGreaterThan(0);
    expect(chunk2.length).toBeGreaterThan(0);

    const reader = readerForChunks([chunk1, chunk2]);
    const { calls, onToken, onCitations, onDone, onError } = recordingHandlers();

    await parseSseStream(reader, { onToken, onCitations, onDone, onError });

    expect(calls).toEqual([{ kind: 'token', payload: 'hello world' }]);
  });

  it('ignores unknown event names without throwing, and keeps parsing subsequent known events', async () => {
    const reader = readerFor(
      sseBody([
        { event: 'token', data: { text: 'a' } },
        { event: 'ping', data: {} },
        { event: 'token', data: { text: 'b' } },
        { event: 'done', data: { session_id: 's', message_id: 'm' } },
      ]),
    );
    const { calls, onToken, onCitations, onDone, onError } = recordingHandlers();

    await parseSseStream(reader, { onToken, onCitations, onDone, onError });

    expect(calls).toEqual([
      { kind: 'token', payload: 'a' },
      { kind: 'token', payload: 'b' },
      { kind: 'done', payload: { session_id: 's', message_id: 'm' } },
    ]);
  });
});

// ---------------------------------------------------------------------------
// useChatStream — the hook, driven end-to-end through a mocked `fetch`.
// ---------------------------------------------------------------------------

describe('useChatStream', () => {
  it('send() immediately appends a user message and accumulates streamed tokens into exactly one assistant message, in order', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      streamResponse([
        { event: 'token', data: { text: 'Roth ' } },
        { event: 'token', data: { text: 'IRAs ' } },
        { event: 'token', data: { text: 'allow tax-free growth.' } },
        {
          event: 'citations',
          data: {
            citations: [{ content_id: 'c-1', title: 'Roth IRA Basics', slug: 'roth-ira-basics' }],
          },
        },
        { event: 'done', data: { session_id: 's-1', message_id: 'm-1' } },
      ]),
    );
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useChatStream());

    act(() => {
      result.current.send('What is a Roth IRA?');
    });

    expect(result.current.messages).toEqual([{ role: 'user', text: 'What is a Roth IRA?' }]);

    await waitFor(() => expect(result.current.streaming).toBe(false));

    const assistantMessages = result.current.messages.filter(
      (message: ChatMessage) => message.role === 'assistant',
    );
    expect(assistantMessages).toHaveLength(1);
    const assistantMessage = assistantMessages[0];
    if (!assistantMessage) {
      throw new Error('expected an assistant message');
    }
    expect(assistantMessage.text).toBe('Roth IRAs allow tax-free growth.');
  });

  it('a citations event attaches the citations array (and no refusal) to the assistant message', async () => {
    const citations = [
      { content_id: 'c-1', title: 'Roth IRA Basics', slug: 'roth-ira-basics' },
      { content_id: 'c-2', title: 'Traditional IRA Basics', slug: 'traditional-ira-basics' },
    ];
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          { event: 'token', data: { text: 'Both are retirement accounts.' } },
          { event: 'citations', data: { citations } },
          { event: 'done', data: { session_id: 's-2', message_id: 'm-2' } },
        ]),
      ),
    );

    const { result } = renderHook(() => useChatStream());
    act(() => {
      result.current.send('Compare IRA types.');
    });
    await waitFor(() => expect(result.current.streaming).toBe(false));

    const assistant = result.current.messages.find(
      (message: ChatMessage) => message.role === 'assistant',
    );
    expect(assistant?.citations).toEqual(citations);
    expect(assistant?.refusal).not.toBe(true);
  });

  it('an empty citations array ([]) flags the assistant message as a refusal', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          { event: 'token', data: { text: 'No published guidance covers this.' } },
          { event: 'citations', data: { citations: [] } },
          { event: 'done', data: { session_id: 's-3', message_id: 'm-3' } },
        ]),
      ),
    );

    const { result } = renderHook(() => useChatStream());
    act(() => {
      result.current.send('An uncovered question.');
    });
    await waitFor(() => expect(result.current.streaming).toBe(false));

    const assistant = result.current.messages.find(
      (message: ChatMessage) => message.role === 'assistant',
    );
    expect(assistant?.citations).toEqual([]);
    expect(assistant?.refusal).toBe(true);
  });

  it('streaming is true immediately after send() and false once the stream completes', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          { event: 'token', data: { text: 'An answer.' } },
          { event: 'citations', data: { citations: [] } },
          { event: 'done', data: { session_id: 's-4', message_id: 'm-4' } },
        ]),
      ),
    );

    const { result } = renderHook(() => useChatStream());
    expect(result.current.streaming).toBe(false);

    act(() => {
      result.current.send('A question.');
    });
    expect(result.current.streaming).toBe(true);

    await waitFor(() => expect(result.current.streaming).toBe(false));
  });

  it("a done event persists session_id to localStorage['advisordesk_session'], and the next send() includes it in the request body", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        streamResponse([
          { event: 'token', data: { text: 'First answer.' } },
          { event: 'citations', data: { citations: [] } },
          { event: 'done', data: { session_id: 'session-abc', message_id: 'm-5' } },
        ]),
      )
      .mockResolvedValueOnce(
        streamResponse([
          { event: 'token', data: { text: 'Second answer.' } },
          { event: 'citations', data: { citations: [] } },
          { event: 'done', data: { session_id: 'session-abc', message_id: 'm-6' } },
        ]),
      );
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useChatStream());
    act(() => {
      result.current.send('First question.');
    });
    await waitFor(() => expect(result.current.streaming).toBe(false));

    expect(localStorage.getItem('advisordesk_session')).toBe('session-abc');

    act(() => {
      result.current.send('Second question.');
    });
    await waitFor(() => expect(result.current.streaming).toBe(false));

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const secondCall = fetchMock.mock.calls[1];
    if (!secondCall) {
      throw new Error('expected a second fetch call');
    }
    const secondCallInit = secondCall[1] as RequestInit;
    expect(secondCallInit.method).toBe('POST');
    const secondBody = JSON.parse(String(secondCallInit.body)) as {
      session_id?: string;
      message?: string;
    };
    expect(secondBody.session_id).toBe('session-abc');
    expect(secondBody.message).toBe('Second question.');
  });

  it("a pre-existing localStorage['advisordesk_session'] value is sent in the request body on the very first send()", async () => {
    localStorage.setItem('advisordesk_session', 'existing-session-id');
    const fetchMock = vi.fn().mockResolvedValue(
      streamResponse([
        { event: 'token', data: { text: 'Answer.' } },
        { event: 'citations', data: { citations: [] } },
        { event: 'done', data: { session_id: 'existing-session-id', message_id: 'm-7' } },
      ]),
    );
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useChatStream());
    act(() => {
      result.current.send('A question.');
    });
    await waitFor(() => expect(result.current.streaming).toBe(false));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const call = fetchMock.mock.calls[0];
    if (!call) {
      throw new Error('expected fetch to have been called');
    }
    const callInit = call[1] as RequestInit;
    expect(callInit.method).toBe('POST');
    const body = JSON.parse(String(callInit.body)) as { session_id?: string };
    expect(body.session_id).toBe('existing-session-id');
  });

  it('a server error event sets error state and stops streaming', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        streamResponse([
          { event: 'token', data: { text: 'Partial ' } },
          {
            event: 'error',
            data: {
              error: {
                code: 'llm_failed',
                message: 'The assistant hit a problem. Please try again.',
              },
            },
          },
        ]),
      ),
    );

    const { result } = renderHook(() => useChatStream());
    act(() => {
      result.current.send('A question that fails mid-stream.');
    });
    await waitFor(() => expect(result.current.streaming).toBe(false));

    expect(result.current.error).toBe('The assistant hit a problem. Please try again.');
  });

  it('an HTTP 429 response before any SSE event sets a friendly, non-JSON error message and does not throw', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonErrorResponse(429, 'rate_limited', 'Too many requests today.')),
    );

    const { result } = renderHook(() => useChatStream());

    expect(() => {
      act(() => {
        result.current.send('One more question.');
      });
    }).not.toThrow();

    await waitFor(() => expect(result.current.streaming).toBe(false));

    expect(result.current.error).toBeTruthy();
    // Never the raw envelope dumped verbatim — a friendly message, not `{"error":{"code":...`.
    expect(result.current.error).not.toMatch(/[{}]/);
    expect(
      result.current.messages.filter((message: ChatMessage) => message.role === 'assistant'),
    ).toHaveLength(0);
  });
});
