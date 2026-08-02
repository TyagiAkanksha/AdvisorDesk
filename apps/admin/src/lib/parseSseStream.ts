// phase-5 task-04 (admin agent panel). Lifted from
// `apps/client/src/components/chat/useChatStream.ts`'s own `parseSseStream` (phase-4 t05,
// read-only reference per this task's brief) into this app's `src/lib/` — the brief's suggested
// placement, since `useAgentStream` is admin's first hand-rolled SSE consumer and
// FRONTEND-CONVENTIONS.md §6 documents this as a pattern shared by BOTH apps' streaming hooks.
// Not a cross-app import (apps never import each other, per repo layering) — an adapted copy,
// same parsing contract, retargeted at PRD §5.4's five events (`token`/`tool_call`/`tool_result`/
// `done`/`error`) instead of §5.3's (`token`/`citations`/`done`/`error`).
//
// Robustness carried over from the source (its own review-round hardening, cited there):
// CRLF-framed streams normalize to LF; a frame split across two `reader.read()` chunks
// (mid-`data:`-line) still parses once the boundary completes; the reader lock is always
// released and the stream is cancelled on an abnormal exit (never pins the HTTP connection
// open); a trailing frame with no closing boundary is flushed once the stream reports `done`.

export interface AgentSseHandlers {
  onToken: (text: string) => void;
  onToolCall: (payload: { tool: string; arguments: unknown }) => void;
  onToolResult: (payload: { tool: string; result_summary: string }) => void;
  onDone: (payload: { tool_calls: unknown }) => void;
  onError: (payload: { code: string; message: string }) => void;
}

/** One parsed `event: <name>\ndata: <json>` frame, before it's dispatched to a handler. */
interface SseFrame {
  event: string;
  data: unknown;
}

/**
 * Extract one SSE field's value from `line` (e.g. `field: "event"` matches `"event: token"` and
 * returns `"token"`). Per the SSE spec, the colon may be followed by at most one leading space,
 * stripped if present. Returns `null` when `line` isn't this field at all.
 */
function parseField(line: string, field: string): string | null {
  const prefix = `${field}:`;
  if (!line.startsWith(prefix)) {
    return null;
  }
  const rest = line.slice(prefix.length);
  return rest.startsWith(' ') ? rest.slice(1) : rest;
}

/**
 * Parse one already-delimited SSE frame body (everything between two frame-boundary newlines,
 * minus the boundary itself) into its event name and JSON-decoded payload. Returns `null` for a
 * frame with no `event:` line or no `data:` line — defensively total rather than throwing.
 */
function parseFrame(frame: string): SseFrame | null {
  let event: string | null = null;
  const dataLines: string[] = [];

  for (const line of frame.split('\n')) {
    const eventValue = parseField(line, 'event');
    if (eventValue !== null) {
      event = eventValue;
      continue;
    }
    const dataValue = parseField(line, 'data');
    if (dataValue !== null) {
      dataLines.push(dataValue);
    }
  }

  if (event === null || dataLines.length === 0) {
    return null;
  }
  return { event, data: JSON.parse(dataLines.join('\n')) as unknown };
}

/**
 * Route one parsed frame to its matching handler; unknown event names are silently ignored
 * (forward-compat). Each payload is validated before use — a malformed `token`/`tool_call`/
 * `tool_result` frame is dropped rather than surfacing `"undefined"` in the UI; `done`/`error`
 * are passed through as opaque payloads (no string-concatenation hazard).
 */
function dispatchFrame(frame: string, handlers: AgentSseHandlers): void {
  const parsed = parseFrame(frame);
  if (parsed === null) {
    return;
  }

  switch (parsed.event) {
    case 'token': {
      const payload = parsed.data as { text?: unknown };
      if (typeof payload.text === 'string') {
        handlers.onToken(payload.text);
      }
      return;
    }
    case 'tool_call': {
      const payload = parsed.data as { tool?: unknown; arguments?: unknown };
      if (typeof payload.tool === 'string') {
        handlers.onToolCall({ tool: payload.tool, arguments: payload.arguments });
      }
      return;
    }
    case 'tool_result': {
      const payload = parsed.data as { tool?: unknown; result_summary?: unknown };
      if (typeof payload.tool === 'string' && typeof payload.result_summary === 'string') {
        handlers.onToolResult({ tool: payload.tool, result_summary: payload.result_summary });
      }
      return;
    }
    case 'done':
      handlers.onDone(parsed.data as { tool_calls: unknown });
      return;
    case 'error':
      handlers.onError((parsed.data as { error: { code: string; message: string } }).error);
      return;
    default:
      return;
  }
}

/**
 * Normalize CRLF line endings to LF across `buffer`. A trailing LONE `\r` (the buffer's very
 * last character) is left untouched — it may be the first half of a `\r\n` pair whose `\n`
 * hasn't arrived yet in a later `reader.read()` chunk.
 */
function normalizeLineEndings(buffer: string): string {
  const hasTrailingLoneCr = buffer.endsWith('\r');
  const body = hasTrailingLoneCr ? buffer.slice(0, -1) : buffer;
  const normalized = body.replace(/\r\n/g, '\n');
  return hasTrailingLoneCr ? `${normalized}\r` : normalized;
}

/**
 * Reads `reader` to exhaustion, splitting the decoded byte stream on frame boundaries (`\n\n`,
 * or the CRLF-normalized equivalent) and dispatching each complete frame to `handlers` as it's
 * found. Always releases the reader lock, and cancels the underlying stream before re-throwing
 * on any abnormal exit.
 *
 * @param reader a `ReadableStreamDefaultReader<Uint8Array>` over an SSE response body.
 * @param handlers per-event callbacks — see `AgentSseHandlers`.
 */
export async function parseSseStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  handlers: AgentSseHandlers,
): Promise<void> {
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (value) {
        buffer = normalizeLineEndings(buffer + decoder.decode(value, { stream: true }));
      }

      let boundary = buffer.indexOf('\n\n');
      while (boundary !== -1) {
        dispatchFrame(buffer.slice(0, boundary), handlers);
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf('\n\n');
      }

      if (done) {
        if (buffer.trim().length > 0) {
          dispatchFrame(buffer, handlers);
        }
        return;
      }
    }
  } catch (err) {
    await reader.cancel().catch(() => {});
    throw err;
  } finally {
    reader.releaseLock();
  }
}
