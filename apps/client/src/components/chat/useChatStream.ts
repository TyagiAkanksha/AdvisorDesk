import { useCallback, useEffect, useRef, useState } from 'react';

import { GENERIC_ERROR_MESSAGE } from '@/lib/copy';
import type { ChatRequest, Citation } from '@/types';

export type { Citation };

// task-05 (phase-4), PRD §5.3, §9; docs/FRONTEND-CONVENTIONS.md §6 ("hand-rolled hooks... using
// fetch + ReadableStream parsing"). Colocated per §3 ("VM hooks are flat and colocated... Args/
// Result declared in-file") — the pinned test-author judgment call (`p4-t05-test-author.md`,
// call #1) keeps `parseSseStream` in this same file rather than a separate module, since
// `useChatStream` is its only caller today; phase-5's `useAgentStream` lifts it later by moving
// the import, not by restructuring this file now.
//
// task-05 review round 1 (`.superpowers/sdd/reports/p4-t05-review.md`) hardened this file on
// five axes ahead of that phase-5 lift: I-3 (localStorage accessors that throw), I-4
// (`parseSseStream`'s reader-lock/cancel cleanup contract), M-3 (CRLF / no-space-field / trailing-
// partial-frame SSE dialects), M-4 (`send()` re-entrancy), M-5 (`AbortController` wired to
// unmount), M-7 (unchecked event payload casts + a citations-with-no-tokens silent-blank path).
// Each finding is annotated at its fix site below.

/** One turn in the conversation (`ChatScreen`'s render list, `MessageBubble`'s prop). */
export interface ChatMessage {
  role: 'user' | 'assistant';
  text: string;
  /** Present once the `citations` event has landed for this assistant turn. */
  citations?: Citation[];
  /** PRD §5.3/§7.5: no published guidance covers the question — an empty `citations` array. */
  refusal?: boolean;
}

/**
 * Per-event callbacks for one `parseSseStream` call. Each handler receives its event's payload
 * UNWRAPPED (e.g. `onError` gets `{code,message}`, not the wire's `{error:{code,message}}`) —
 * test-author judgment call #2, `p4-t05-test-author.md`: that's what every caller actually wants.
 */
export interface SseHandlers {
  onToken: (text: string) => void;
  onCitations: (citations: Citation[]) => void;
  onDone: (payload: { session_id: string; message_id: string }) => void;
  onError: (payload: { code: string; message: string }) => void;
}

/** One parsed `event: <name>\ndata: <json>` frame, before it's dispatched to a handler. */
interface SseFrame {
  event: string;
  data: unknown;
}

/**
 * Extract one SSE field's value from `line` (e.g. `field: "event"` matches `"event: token"` and
 * returns `"token"`). Per the SSE spec, the colon may be followed by AT MOST one leading space,
 * which is stripped if present — so both `data: {...}` (this app's real wire, LF + space) and
 * the spec-legal `data:{...}` (no space) parse identically. Returns `null` when `line` isn't
 * this field at all (review round 1, M-3, probe P-A6).
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
 * minus the boundary itself) into its event name and JSON-decoded payload.
 *
 * Returns `null` for a frame with no `event:` line or no `data:` line — defensively total rather
 * than throwing, though every real frame from `apps/api/app/routes/sse.py::sse_event` always
 * carries both.
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

/** Route one parsed frame to its matching handler; unknown event names are silently ignored
 * (test-author judgment call #5: forward-compat with phase-5's richer `useAgentStream` event
 * set — `/public/chat` itself only ever emits `token`/`citations`/`done`/`error`, PRD §5.3).
 *
 * task-05 review round 1, M-7: each payload is validated before use rather than blindly cast —
 * a `token` event whose `data.text` isn't a string is ignored outright (never appends the
 * literal string `"undefined"` to the answer, probe P-A11); a `citations` event whose
 * `data.citations` isn't an array is likewise ignored. `done`/`error` are left as direct casts:
 * both are only ever consumed as opaque pass-through payloads (a session/message id string pair,
 * an error code/message pair) with no string-concatenation hazard the way `onToken` has. */
function dispatchFrame(frame: string, handlers: SseHandlers): void {
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
    case 'citations': {
      const payload = parsed.data as { citations?: unknown };
      if (Array.isArray(payload.citations)) {
        handlers.onCitations(payload.citations as Citation[]);
      }
      return;
    }
    case 'done':
      handlers.onDone(parsed.data as { session_id: string; message_id: string });
      return;
    case 'error':
      handlers.onError((parsed.data as { error: { code: string; message: string } }).error);
      return;
    default:
      return;
  }
}

/**
 * Normalize CRLF line endings to LF across `buffer` (review round 1, M-3, probes P-A5/P-A7: a
 * CRLF-framed stream — `\r\n\r\n` boundaries — previously yielded zero events, since the parser
 * only ever searched for bare `\n\n`). Safe to run unconditionally on the whole accumulated
 * buffer on every chunk: a raw, unescaped `\r` byte can never legitimately appear INSIDE a
 * `data:` line's JSON payload (JSON requires control characters to be escaped, e.g. `\r` as the
 * two-character sequence backslash-r, never a literal 0x0D byte) — so every `\r` this function
 * sees is SSE framing, never token content, and converting it is always correct.
 *
 * A trailing LONE `\r` (the buffer's very last character) is left untouched: it may be the first
 * half of a `\r\n` pair whose `\n` hasn't arrived yet in a later `reader.read()` chunk —
 * normalizing it away here would silently swallow that pairing once it does arrive.
 */
function normalizeLineEndings(buffer: string): string {
  const hasTrailingLoneCr = buffer.endsWith('\r');
  const body = hasTrailingLoneCr ? buffer.slice(0, -1) : buffer;
  const normalized = body.replace(/\r\n/g, '\n');
  return hasTrailingLoneCr ? `${normalized}\r` : normalized;
}

/**
 * Standalone SSE parser (liftable for phase-5's `useAgentStream`, per the task brief). Reads
 * `reader` to exhaustion, splitting the decoded byte stream on frame boundaries (`\n\n`, or the
 * CRLF-normalized equivalent of `\r\n\r\n` — M-3) and dispatching each complete frame to
 * `handlers` as it's found — including a frame whose bytes arrive split across two
 * `reader.read()` chunks, mid-`data:`-line (the real-network case `useChatStream.test.ts`'s test
 * #2 pins): `TextDecoder`'s `{stream: true}` mode plus a string buffer that only ever consumes up
 * through the last complete boundary handles this — a chunk boundary never loses or duplicates a
 * byte, it just delays a frame becoming completable until enough chunks have arrived.
 *
 * Two contract guarantees added in review round 1, since this function is designated for
 * phase-5's lift and its contract is therefore public, not just this hook's private detail:
 *
 * - **I-4 (cleanup):** a `try/finally` always releases the reader lock
 *   (`reader.releaseLock()`), and a `catch` cancels the underlying stream
 *   (`reader.cancel()`) before re-throwing on any abnormal exit (e.g. malformed JSON) — probe
 *   P-A10 showed a throw previously left `stream.locked === true` with no cancellation, pinning
 *   the HTTP connection open in a real browser until GC.
 * - **M-3 (trailing partial frame):** once `reader.read()` reports `done`, any non-whitespace
 *   bytes still sitting in the buffer with no closing boundary are flushed as one last frame
 *   (probe P-A7: a stream that closes right after its final frame's `data:` line, with no
 *   trailing blank line, previously dropped that frame — including a `done` event, meaning the
 *   session id was never persisted).
 *
 * @param reader a `ReadableStreamDefaultReader<Uint8Array>` over an SSE response body (e.g.
 *   `response.body.getReader()`).
 * @param handlers per-event callbacks — see `SseHandlers`.
 */
export async function parseSseStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  handlers: SseHandlers,
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
    // I-4: an abnormal exit must not leave the underlying HTTP response pinned open — cancel it
    // before letting the error propagate to the caller. `.catch(() => {})` guards against a
    // second exception (e.g. cancelling an already-errored stream) masking the original one.
    await reader.cancel().catch(() => {});
    throw err;
  } finally {
    reader.releaseLock();
  }
}

const SESSION_STORAGE_KEY = 'advisordesk_session';
// Browser-reachable API origin: this hook runs client-side, so (unlike `src/lib/publicApi.ts`'s
// server-only `API_URL`) it needs a `NEXT_PUBLIC_`-prefixed var to be inlined into the JS bundle
// at build time — the same mechanism/idiom `apps/admin/src/lib/apiBase.ts` already uses for its
// own (also browser-side) RTK Query base URL. Dev/test fall back to the documented local API
// origin so an unset var never blocks `pnpm dev`/`pnpm test`; production fails loudly at request
// time instead of silently shipping a request to `undefined/api/v1/public/chat`.
const DEV_FALLBACK_API_URL = 'http://localhost:8000';

function resolveApiBaseUrl(): string {
  const value = process.env.NEXT_PUBLIC_API_URL;
  if (value) {
    return value;
  }
  if (process.env.NODE_ENV === 'production') {
    throw new Error('NEXT_PUBLIC_API_URL must be set at build time');
  }
  return DEV_FALLBACK_API_URL;
}

/**
 * PRD §5.3: session id lives in `localStorage` only (no cookies) — read before every `send()`,
 * not cached in React state, so a value written by an earlier tab/reload is always picked up.
 *
 * task-05 review round 1, I-3: wrapped in `try/catch`, not just a `typeof` guard. `typeof
 * localStorage === 'undefined'` only covers a MISSING global (Node/SSR, Firefox
 * `dom.storage.enabled=false`); it does not catch a *throwing* one — Chrome's per-site "block
 * cookies" setting, a `<iframe sandbox>` without `allow-same-origin`, and quota/security failures
 * all throw `SecurityError`/`QuotaExceededError` on access. Probe P-C1: without this catch, a
 * throwing accessor died before `fetch` was ever issued, with copy that blamed the network. PRD
 * §5.3 makes `localStorage` the only session transport, so a throwing accessor degrades to
 * stateless single-turn chat (returns `null`, same as "no session yet"), never blocks sending.
 */
function readStoredSessionId(): string | null {
  try {
    if (typeof localStorage === 'undefined') {
      return null;
    }
    return localStorage.getItem(SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

/** Write half of I-3 (see `readStoredSessionId`): a throwing `setItem` (quota exceeded, blocked
 * storage) must not turn an already-successful, already-streamed answer into an error banner
 * (probe P-B7) — silently proceed without persistence; the next `send()` simply won't have a
 * session id to resend, degrading to a fresh session rather than failing the exchange that just
 * completed. */
function persistSessionId(sessionId: string): void {
  try {
    if (typeof localStorage === 'undefined') {
      return;
    }
    localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  } catch {
    // Intentionally swallowed — see docstring above.
  }
}

/**
 * Turn a non-2xx `/public/chat` response (PRD §9: e.g. a 429 rate-limit rejection) into a
 * friendly, never-raw-JSON message — the §9 envelope's own `.message` field is already
 * human-authored copy (`apps/api/app/routes/ratelimit.py`'s `_PER_MIN_MESSAGE` etc.), so
 * surfacing it directly satisfies "frontends surface friendly messages" without the client
 * inventing its own wording. Falls back to the shared generic message if the body isn't the
 * expected envelope shape at all (e.g. a network intermediary's own error page) — never dumps
 * the raw body text.
 */
async function friendlyErrorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { error?: { message?: string } };
    if (body.error?.message) {
      return body.error.message;
    }
  } catch {
    // Unparsable body — fall through to the generic message below.
  }
  return GENERIC_ERROR_MESSAGE;
}

/** Append `chunk` to the in-progress assistant message, starting a new one on the first token
 * of a turn. Pure — returns a new array, never mutates `messages`. */
function appendAssistantToken(
  messages: ChatMessage[],
  chunk: string,
  isFirstToken: boolean,
): ChatMessage[] {
  const last = messages[messages.length - 1];
  if (isFirstToken || last === undefined || last.role !== 'assistant') {
    return [...messages, { role: 'assistant', text: chunk }];
  }
  return [...messages.slice(0, -1), { ...last, text: last.text + chunk }];
}

/**
 * Attach `citations` to the in-progress assistant message; an empty array flags it as a refusal
 * (PRD §7.4/§7.5 — no published guidance covers the question). Pure.
 *
 * task-05 review round 1, M-7 (probe P-C2): previously a no-op when the last message wasn't an
 * assistant turn, which silently dropped a `citations` event that arrives with NO preceding
 * `token` (e.g. the model streamed zero tokens before citing) — no assistant bubble, no error,
 * a silent blank region FRONTEND-CONVENTIONS.md §9 forbids. Now it starts a (empty-text)
 * assistant turn in that case instead, so the exchange always surfaces *something*.
 */
function attachCitations(messages: ChatMessage[], citations: Citation[]): ChatMessage[] {
  const last = messages[messages.length - 1];
  if (last !== undefined && last.role === 'assistant') {
    return [...messages.slice(0, -1), { ...last, citations, refusal: citations.length === 0 }];
  }
  return [...messages, { role: 'assistant', text: '', citations, refusal: citations.length === 0 }];
}

export interface UseChatStreamResult {
  messages: ChatMessage[];
  streaming: boolean;
  error: string | null;
  send: (text: string) => void;
}

/**
 * The client chat screen's VM hook (PRD §5.3, §7; docs/FRONTEND-CONVENTIONS.md §6). Posts to
 * `POST /api/v1/public/chat`, streams the typed SSE events into `messages`/`streaming`/`error`,
 * and round-trips the session id through `localStorage['advisordesk_session']` — no cookies.
 */
export function useChatStream(): UseChatStreamResult {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // M-4: a `streamingRef` mirror of the `streaming` state, read synchronously by `send()`'s
  // re-entrancy guard below. A plain `streaming` state read inside the `useCallback([])` body
  // would close over a stale value (the callback's identity never changes, so it would keep
  // seeing whatever `streaming` was on first render); a ref sidesteps that without adding
  // `streaming` to the dependency array (which would churn `send`'s identity on every stream
  // start/stop for no benefit — nothing downstream depends on that).
  const streamingRef = useRef(false);
  const setStreamingState = useCallback((value: boolean) => {
    streamingRef.current = value;
    setStreaming(value);
  }, []);

  // M-5: the in-flight request's `AbortController`, if any — aborted on unmount below, and
  // cleared once its exchange finishes (success, failure, or abort) so a later `send()` always
  // starts from a fresh controller.
  const abortControllerRef = useRef<AbortController | null>(null);
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const send = useCallback(
    (text: string) => {
      // M-4 (probe P-B1): a re-entrancy no-op. `ChatScreen` already disables its controls while
      // streaming, but that invariant belongs in the state machine that owns `streaming`, not only
      // in a dumb component that happens to remember to guard it — a second concurrent `send()`
      // previously issued a second `fetch`, created a second assistant message, and let whichever
      // stream finished first flip `streaming` back to `false` while the other was still writing.
      if (streamingRef.current) {
        return;
      }

      // Synchronous prefix: the user's turn and `streaming: true` both land before this function
      // returns (`useChatStream.test.ts`'s "streaming is true immediately after send()" pins this
      // — an async function's body runs synchronously up to its first `await`).
      setError(null);
      setMessages((prev) => [...prev, { role: 'user', text }]);
      setStreamingState(true);

      let firstTokenSeen = false;
      const controller = new AbortController();
      abortControllerRef.current = controller;

      void (async () => {
        try {
          const sessionId = readStoredSessionId();
          const payload: ChatRequest = { message: text, session_id: sessionId ?? undefined };
          const response = await fetch(`${resolveApiBaseUrl()}/api/v1/public/chat`, {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify(payload),
            signal: controller.signal,
          });

          if (!response.ok) {
            setError(await friendlyErrorMessage(response));
            return;
          }

          const body = response.body;
          if (body === null) {
            setError(GENERIC_ERROR_MESSAGE);
            return;
          }

          await parseSseStream(body.getReader(), {
            onToken: (chunk) => {
              setMessages((prev) => appendAssistantToken(prev, chunk, !firstTokenSeen));
              firstTokenSeen = true;
            },
            onCitations: (citations) => {
              setMessages((prev) => attachCitations(prev, citations));
            },
            onDone: ({ session_id }) => {
              persistSessionId(session_id);
            },
            onError: ({ message }) => {
              setError(message);
            },
          });
        } catch {
          // M-5: an abort we ourselves triggered (unmount) is not a failure the user needs to see
          // — surfacing a friendly error banner for a request the component itself cancelled would
          // be misleading (and, for the unmount case, nothing is even left mounted to show it to).
          if (!controller.signal.aborted) {
            setError(GENERIC_ERROR_MESSAGE);
          }
        } finally {
          if (abortControllerRef.current === controller) {
            abortControllerRef.current = null;
          }
          setStreamingState(false);
        }
      })();
    },
    [setStreamingState],
  );

  return { messages, streaming, error, send };
}
