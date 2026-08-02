import { afterEach, describe, expect, it, vi } from 'vitest';

import type { AgentSseHandlers } from './parseSseStream';
import { parseSseStream } from './parseSseStream';

// phase-5 task-04 review round 1 (`.superpowers/sdd/reports/p5-t04-review.md`), finding I-2 —
// implementer-authored fix-round test file (not test-author-pinned; per the coordinator's
// fix-round dispatch, new behavior/coverage gets a new file). `parseSseStream.ts` is a 171-line
// lifted copy of `apps/client/src/components/chat/useChatStream.ts`'s own `parseSseStream`
// (phase-4 t05 review-round hardening), retargeted at PRD §5.4's five events instead of §5.3's
// four — but the admin app that now OWNS this copy had no direct test exercising it; every
// existing admin SSE fixture enqueues one already-LF-framed chunk, so the CRLF, split-frame,
// multi-line-`data:`, no-space-field, trailing-partial-frame, and reader-cleanup paths were never
// exercised. This file ports the client's two dedicated parser test files
// (`parseSseStream.guards.test.ts`, and the `describe('parseSseStream', …)` block of the pinned
// `useChatStream.test.ts`) adapted to this module's location and PRD §5.4 event set
// (`token`/`tool_call`/`tool_result`/`done`/`error`, no `citations`), covering the reviewer's
// full 10-probe list (P1–P10 in the review's "P-A" section).
//
// Local helpers only — this module has no pinned test file of its own to avoid coupling to.

interface SseFrame {
  event: string;
  data: unknown;
}

function sseBody(frames: SseFrame[], separator = '\n\n', fieldSeparator = ': '): string {
  return frames
    .map(
      (frame) =>
        `event${fieldSeparator}${frame.event}\ndata${fieldSeparator}${JSON.stringify(frame.data)}${separator}`,
    )
    .join('');
}

function readerForChunks(chunks: string[]): {
  reader: ReadableStreamDefaultReader<Uint8Array>;
  stream: ReadableStream<Uint8Array>;
} {
  const encoded = chunks.map((chunk) => new TextEncoder().encode(chunk));
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of encoded) {
        controller.enqueue(chunk);
      }
      controller.close();
    },
  });
  return { reader: stream.getReader(), stream };
}

function readerForBody(body: string): {
  reader: ReadableStreamDefaultReader<Uint8Array>;
  stream: ReadableStream<Uint8Array>;
} {
  return readerForChunks([body]);
}

interface RecordedEvent {
  kind: 'token' | 'tool_call' | 'tool_result' | 'done' | 'error';
  payload: unknown;
}

function recordingHandlers(): { calls: RecordedEvent[]; handlers: AgentSseHandlers } {
  const calls: RecordedEvent[] = [];
  return {
    calls,
    handlers: {
      onToken: (text) => calls.push({ kind: 'token', payload: text }),
      onToolCall: (payload) => calls.push({ kind: 'tool_call', payload }),
      onToolResult: (payload) => calls.push({ kind: 'tool_result', payload }),
      onDone: (payload) => calls.push({ kind: 'done', payload }),
      onError: (payload) => calls.push({ kind: 'error', payload }),
    },
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('parseSseStream — P1 CRLF-framed stream', () => {
  it('parses tokens, a tool_call, and done from a fully \\r\\n\\r\\n-boundaried stream', async () => {
    const argumentsFixture = { title: 'Roth IRA Conversion Basics' };
    const body = sseBody([
      { event: 'token', data: { text: 'Creating ' } },
      { event: 'token', data: { text: 'the draft.' } },
      { event: 'tool_call', data: { tool: 'create_draft', arguments: argumentsFixture } },
      { event: 'done', data: { tool_calls: [] } },
    ]).replace(/\n/g, '\r\n');
    const { reader } = readerForBody(body);
    const { calls, handlers } = recordingHandlers();

    await parseSseStream(reader, handlers);

    expect(calls).toEqual([
      { kind: 'token', payload: 'Creating ' },
      { kind: 'token', payload: 'the draft.' },
      { kind: 'tool_call', payload: { tool: 'create_draft', arguments: argumentsFixture } },
      { kind: 'done', payload: { tool_calls: [] } },
    ]);
  });
});

describe('parseSseStream — P2 frame split mid-`data:`-line', () => {
  it('reassembles a tool_result whose bytes are split across two reader.read() chunks', async () => {
    const resultSummary = 'Created draft d-42 (Roth IRA Conversion Basics).';
    const full = `event: tool_result\ndata: {"tool":"create_draft","result_summary":"${resultSummary}"}\n\n`;
    const splitAt = full.indexOf('Roth IRA') + 4;
    const chunk1 = full.slice(0, splitAt);
    const chunk2 = full.slice(splitAt);
    expect(chunk1.length).toBeGreaterThan(0);
    expect(chunk2.length).toBeGreaterThan(0);

    const { reader } = readerForChunks([chunk1, chunk2]);
    const { calls, handlers } = recordingHandlers();

    await parseSseStream(reader, handlers);

    expect(calls).toEqual([
      { kind: 'tool_result', payload: { tool: 'create_draft', result_summary: resultSummary } },
    ]);
  });
});

describe('parseSseStream — P3 split INSIDE a \\r\\n pair', () => {
  it('carries a trailing lone `\\r` over to the next chunk instead of losing the frame boundary', async () => {
    const full =
      'event: token\r\ndata: {"text":"a"}\r\n\r\nevent: token\r\ndata: {"text":"b"}\r\n\r\n';
    // The boundary between the two frames is the 4-byte run `\r\n\r\n`. Split so chunk1 ends
    // with the boundary's THIRD byte (a lone `\r`) and chunk2 begins with its fourth (`\n`) —
    // i.e. squarely inside the second `\r\n` pair, not at a frame edge.
    const boundaryIndex = full.indexOf('\r\n\r\n', full.indexOf('"a"'));
    const splitAt = boundaryIndex + 3;
    const chunk1 = full.slice(0, splitAt);
    const chunk2 = full.slice(splitAt);
    expect(chunk1.endsWith('\r')).toBe(true);
    expect(chunk2.startsWith('\n')).toBe(true);

    const { reader } = readerForChunks([chunk1, chunk2]);
    const { calls, handlers } = recordingHandlers();

    await parseSseStream(reader, handlers);

    expect(calls).toEqual([
      { kind: 'token', payload: 'a' },
      { kind: 'token', payload: 'b' },
    ]);
  });
});

describe('parseSseStream — P4 multi-line `data:`', () => {
  it('joins two `data:` lines with `\\n` before JSON.parse', async () => {
    const body =
      'event: tool_result\ndata: {"tool":"create_draft",\ndata: "result_summary":"Created it."}\n\n';
    const { reader } = readerForBody(body);
    const { calls, handlers } = recordingHandlers();

    await parseSseStream(reader, handlers);

    expect(calls).toEqual([
      { kind: 'tool_result', payload: { tool: 'create_draft', result_summary: 'Created it.' } },
    ]);
  });
});

describe('parseSseStream — P5 spec-legal no-space field', () => {
  it('parses `data:`/`event:` fields with no leading space', async () => {
    const body = sseBody([{ event: 'token', data: { text: 'hi' } }], '\n\n', ':');
    const { reader } = readerForBody(body);
    const { calls, handlers } = recordingHandlers();

    await parseSseStream(reader, handlers);

    expect(calls).toEqual([{ kind: 'token', payload: 'hi' }]);
  });
});

describe('parseSseStream — P6 trailing partial frame', () => {
  it('flushes a trailing `done` frame with no closing blank line before the stream ends', async () => {
    const body = 'event: token\ndata: {"text":"a"}\n\n' + 'event: done\ndata: {"tool_calls":[]}';
    const { reader } = readerForBody(body);
    const { calls, handlers } = recordingHandlers();

    await parseSseStream(reader, handlers);

    expect(calls).toEqual([
      { kind: 'token', payload: 'a' },
      { kind: 'done', payload: { tool_calls: [] } },
    ]);
  });

  it('does not flush a trailing all-whitespace remainder as a spurious frame', async () => {
    const body = 'event: token\ndata: {"text":"a"}\n\n   \n';
    const { reader } = readerForBody(body);
    const { calls, handlers } = recordingHandlers();

    await parseSseStream(reader, handlers);

    expect(calls).toEqual([{ kind: 'token', payload: 'a' }]);
  });
});

describe('parseSseStream — P7 unknown event name', () => {
  it('ignores an unknown event without throwing, and keeps parsing subsequent known events', async () => {
    const body = sseBody([
      { event: 'token', data: { text: 'a' } },
      { event: 'heartbeat', data: {} },
      { event: 'token', data: { text: 'b' } },
      { event: 'done', data: { tool_calls: [] } },
    ]);
    const { reader } = readerForBody(body);
    const { calls, handlers } = recordingHandlers();

    await parseSseStream(reader, handlers);

    expect(calls).toEqual([
      { kind: 'token', payload: 'a' },
      { kind: 'token', payload: 'b' },
      { kind: 'done', payload: { tool_calls: [] } },
    ]);
  });
});

describe('parseSseStream — P8 malformed payloads are dropped, never surfacing "undefined"', () => {
  it('ignores a token event whose data has no string `text`', async () => {
    const body = sseBody([
      { event: 'token', data: { text: 42 } },
      { event: 'token', data: { text: 'ok' } },
    ]);
    const { reader } = readerForBody(body);
    const { calls, handlers } = recordingHandlers();

    await parseSseStream(reader, handlers);

    expect(calls).toEqual([{ kind: 'token', payload: 'ok' }]);
  });

  it('ignores a tool_call event whose data has no string `tool`', async () => {
    const body = sseBody([
      { event: 'tool_call', data: { arguments: { a: 1 } } },
      { event: 'tool_call', data: { tool: 'create_draft', arguments: {} } },
    ]);
    const { reader } = readerForBody(body);
    const { calls, handlers } = recordingHandlers();

    await parseSseStream(reader, handlers);

    expect(calls).toEqual([
      { kind: 'tool_call', payload: { tool: 'create_draft', arguments: {} } },
    ]);
  });

  it('ignores a tool_result event whose data has no string `result_summary`', async () => {
    const body = sseBody([
      { event: 'tool_result', data: { tool: 'create_draft' } },
      { event: 'tool_result', data: { tool: 'create_draft', result_summary: 'ok' } },
    ]);
    const { reader } = readerForBody(body);
    const { calls, handlers } = recordingHandlers();

    await parseSseStream(reader, handlers);

    expect(calls).toEqual([
      { kind: 'tool_result', payload: { tool: 'create_draft', result_summary: 'ok' } },
    ]);
  });
});

describe('parseSseStream — P9 cleanup: reader-lock release + cancel-on-abnormal-exit', () => {
  it('releases the reader lock after a normal, fully-drained stream', async () => {
    const { reader, stream } = readerForBody(sseBody([{ event: 'token', data: { text: 'hi' } }]));
    const { handlers } = recordingHandlers();

    await parseSseStream(reader, handlers);

    expect(stream.locked).toBe(false);
  });

  it('releases the reader lock AND cancels the stream when a malformed frame throws mid-parse', async () => {
    const { reader, stream } = readerForBody('event: token\ndata: {not valid json\n\n');
    const cancelSpy = vi.spyOn(reader, 'cancel');
    const { handlers } = recordingHandlers();

    await expect(parseSseStream(reader, handlers)).rejects.toThrow();

    expect(cancelSpy).toHaveBeenCalledTimes(1);
    expect(stream.locked).toBe(false);
  });
});

describe('parseSseStream — P10 `error` frame unwrapping', () => {
  it('unwraps `{error:{code,message}}` to `{code,message}`', async () => {
    const body = sseBody([
      { event: 'error', data: { error: { code: 'agent_stream_failed', message: 'Boom.' } } },
    ]);
    const { reader } = readerForBody(body);
    const { calls, handlers } = recordingHandlers();

    await parseSseStream(reader, handlers);

    expect(calls).toEqual([
      { kind: 'error', payload: { code: 'agent_stream_failed', message: 'Boom.' } },
    ]);
  });
});
