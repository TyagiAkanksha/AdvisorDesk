// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';

import { parseSseStream } from './useChatStream';

// task-05 review round 1 (`.superpowers/sdd/reports/p4-t05-review.md`) — implementer-authored
// (not test-author-pinned; per the coordinator's fix-round dispatch, new behavior gets new test
// files, e.g. this one, rather than edits to the four pinned files). Covers `parseSseStream`'s
// hardening: I-4 (reader-lock release + stream cancellation on abnormal exit), M-3 (CRLF framing,
// `data:`/`event:` fields with no leading space, a trailing partial frame at stream end), and the
// parser half of M-7 (a `token` event whose `data.text` isn't a string is ignored, never appends
// the literal string "undefined").
//
// Local helpers only — deliberately NOT imported from the pinned `useChatStream.test.ts` (this
// file must stand on its own and never risk coupling to, or drifting from, a pinned fixture).

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

function readerForBody(body: string): {
  reader: ReadableStreamDefaultReader<Uint8Array>;
  stream: ReadableStream<Uint8Array>;
} {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(body));
      controller.close();
    },
  });
  return { reader: stream.getReader(), stream };
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

afterEach(() => {
  vi.restoreAllMocks();
});

describe('parseSseStream — I-4 cleanup contract', () => {
  it('releases the reader lock after a normal, fully-drained stream', async () => {
    const { reader, stream } = readerForBody(sseBody([{ event: 'token', data: { text: 'hi' } }]));
    const { onToken, onCitations, onDone, onError } = recordingHandlers();

    await parseSseStream(reader, { onToken, onCitations, onDone, onError });

    expect(stream.locked).toBe(false);
  });

  it('releases the reader lock AND cancels the stream when a malformed frame throws mid-parse', async () => {
    const { reader, stream } = readerForBody('event: token\ndata: {not valid json\n\n');
    const cancelSpy = vi.spyOn(reader, 'cancel');
    const { onToken, onCitations, onDone, onError } = recordingHandlers();

    await expect(
      parseSseStream(reader, { onToken, onCitations, onDone, onError }),
    ).rejects.toThrow();

    expect(cancelSpy).toHaveBeenCalledTimes(1);
    expect(stream.locked).toBe(false);
  });
});

describe('parseSseStream — M-3 tolerant framing', () => {
  it('parses a CRLF-framed stream (\\r\\n\\r\\n boundaries)', async () => {
    // Build the plain LF body first, then blanket-convert EVERY `\n` (both the internal
    // `event:`/`data:` line break and the `\n\n` frame terminator) to `\r\n` in one pass — turns
    // `\n\n` into `\r\n\r\n` and `event: token\ndata: ...` into `event: token\r\ndata: ...`,
    // matching a real CRLF-framed SSE dialect exactly.
    const body = sseBody([
      { event: 'token', data: { text: 'hi' } },
      { event: 'done', data: { session_id: 's', message_id: 'm' } },
    ]).replace(/\n/g, '\r\n');
    const { reader } = readerForBody(body);
    const { calls, onToken, onCitations, onDone, onError } = recordingHandlers();

    await parseSseStream(reader, { onToken, onCitations, onDone, onError });

    expect(calls).toEqual([
      { kind: 'token', payload: 'hi' },
      { kind: 'done', payload: { session_id: 's', message_id: 'm' } },
    ]);
  });

  it('parses `data:`/`event:` fields with no leading space (spec-legal SSE)', async () => {
    const body = sseBody([{ event: 'token', data: { text: 'hi' } }], '\n\n', ':');
    const { reader } = readerForBody(body);
    const { calls, onToken, onCitations, onDone, onError } = recordingHandlers();

    await parseSseStream(reader, { onToken, onCitations, onDone, onError });

    expect(calls).toEqual([{ kind: 'token', payload: 'hi' }]);
  });

  it('flushes a trailing frame that has no closing blank line before the stream ends', async () => {
    // The first frame is properly terminated; the second (the stream's last) is not — the
    // server/connection just stops right after its `data:` line.
    const body =
      'event: token\ndata: {"text":"a"}\n\n' +
      'event: done\ndata: {"session_id":"s","message_id":"m"}';
    const { reader } = readerForBody(body);
    const { calls, onToken, onCitations, onDone, onError } = recordingHandlers();

    await parseSseStream(reader, { onToken, onCitations, onDone, onError });

    expect(calls).toEqual([
      { kind: 'token', payload: 'a' },
      { kind: 'done', payload: { session_id: 's', message_id: 'm' } },
    ]);
  });

  it('does not flush a trailing all-whitespace remainder as a spurious frame', async () => {
    const body = 'event: token\ndata: {"text":"a"}\n\n   \n';
    const { reader } = readerForBody(body);
    const { calls, onToken, onCitations, onDone, onError } = recordingHandlers();

    await parseSseStream(reader, { onToken, onCitations, onDone, onError });

    expect(calls).toEqual([{ kind: 'token', payload: 'a' }]);
  });
});

describe('parseSseStream — M-7 payload validation (parser half)', () => {
  it('ignores a token event whose data has no string `text`, never appending "undefined"', async () => {
    const body = sseBody([
      { event: 'token', data: { oops: true } },
      { event: 'token', data: { text: 'ok' } },
    ]);
    const { reader } = readerForBody(body);
    const { calls, onToken, onCitations, onDone, onError } = recordingHandlers();

    await parseSseStream(reader, { onToken, onCitations, onDone, onError });

    expect(calls).toEqual([{ kind: 'token', payload: 'ok' }]);
  });

  it('ignores a citations event whose data.citations is not an array', async () => {
    const body = sseBody([
      { event: 'citations', data: { citations: 'not-an-array' } },
      { event: 'done', data: { session_id: 's', message_id: 'm' } },
    ]);
    const { reader } = readerForBody(body);
    const { calls, onToken, onCitations, onDone, onError } = recordingHandlers();

    await parseSseStream(reader, { onToken, onCitations, onDone, onError });

    expect(calls).toEqual([{ kind: 'done', payload: { session_id: 's', message_id: 'm' } }]);
  });
});
