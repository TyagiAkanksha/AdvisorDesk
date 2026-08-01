import { useCallback, useState } from 'react';

import type { ChatRequest, Citation } from '@/types';

export type { Citation };

// task-05 (phase-4), PRD §5.3, §9; docs/FRONTEND-CONVENTIONS.md §6 ("hand-rolled hooks... using
// fetch + ReadableStream parsing"). Colocated per §3 ("VM hooks are flat and colocated... Args/
// Result declared in-file") — the pinned test-author judgment call (`p4-t05-test-author.md`,
// call #1) keeps `parseSseStream` in this same file rather than a separate module, since
// `useChatStream` is its only caller today; phase-5's `useAgentStream` lifts it later by moving
// the import, not by restructuring this file now.

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
 * Parse one already-delimited SSE frame body (everything between two `\n\n` boundaries, minus
 * the trailing boundary itself) into its event name and JSON-decoded payload.
 *
 * Returns `null` for a frame with no `event:` line or no `data:` line — defensively total rather
 * than throwing, though every real frame from `apps/api/app/routes/sse.py::sse_event` always
 * carries both.
 */
function parseFrame(frame: string): SseFrame | null {
  let event: string | null = null;
  const dataLines: string[] = [];

  for (const line of frame.split('\n')) {
    if (line.startsWith('event: ')) {
      event = line.slice('event: '.length);
    } else if (line.startsWith('data: ')) {
      dataLines.push(line.slice('data: '.length));
    }
  }

  if (event === null || dataLines.length === 0) {
    return null;
  }
  return { event, data: JSON.parse(dataLines.join('\n')) as unknown };
}

/** Route one parsed frame to its matching handler; unknown event names are silently ignored
 * (test-author judgment call #5: forward-compat with phase-5's richer `useAgentStream` event
 * set — `/public/chat` itself only ever emits `token`/`citations`/`done`/`error`, PRD §5.3). */
function dispatchFrame(frame: string, handlers: SseHandlers): void {
  const parsed = parseFrame(frame);
  if (parsed === null) {
    return;
  }

  switch (parsed.event) {
    case 'token':
      handlers.onToken((parsed.data as { text: string }).text);
      return;
    case 'citations':
      handlers.onCitations((parsed.data as { citations: Citation[] }).citations);
      return;
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
 * Standalone SSE parser (liftable for phase-5's `useAgentStream`, per the task brief). Reads
 * `reader` to exhaustion, splitting the decoded byte stream on `\n\n` frame boundaries and
 * dispatching each complete frame to `handlers` as it's found — including a frame whose bytes
 * arrive split across two `reader.read()` chunks, mid-`data:`-line (the real-network case
 * `useChatStream.test.ts`'s test #2 pins): `TextDecoder`'s `{stream: true}` mode plus a
 * string buffer that only ever consumes up through the last complete `\n\n` handles this — a
 * chunk boundary never loses or duplicates a byte, it just delays a frame becoming completable
 * until enough chunks have arrived.
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

  for (;;) {
    const { done, value } = await reader.read();
    if (value) {
      buffer += decoder.decode(value, { stream: true });
    }

    let boundary = buffer.indexOf('\n\n');
    while (boundary !== -1) {
      dispatchFrame(buffer.slice(0, boundary), handlers);
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf('\n\n');
    }

    if (done) {
      return;
    }
  }
}

const SESSION_STORAGE_KEY = 'advisordesk_session';
const GENERIC_ERROR_MESSAGE = 'Something went wrong. Please try again.';
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

/** PRD §5.3: session id lives in `localStorage` only (no cookies) — read before every `send()`,
 * not cached in React state, so a value written by an earlier tab/reload is always picked up. */
function readStoredSessionId(): string | null {
  if (typeof localStorage === 'undefined') {
    return null;
  }
  return localStorage.getItem(SESSION_STORAGE_KEY);
}

function persistSessionId(sessionId: string): void {
  if (typeof localStorage === 'undefined') {
    return;
  }
  localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
}

/**
 * Turn a non-2xx `/public/chat` response (PRD §9: e.g. a 429 rate-limit rejection) into a
 * friendly, never-raw-JSON message — the §9 envelope's own `.message` field is already
 * human-authored copy (`apps/api/app/routes/ratelimit.py`'s `_PER_MIN_MESSAGE` etc.), so
 * surfacing it directly satisfies "frontends surface friendly messages" without the client
 * inventing its own wording. Falls back to a generic message if the body isn't the expected
 * envelope shape at all (e.g. a network intermediary's own error page) — never dumps the raw
 * body text.
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

/** Attach `citations` to the in-progress assistant message; an empty array flags it as a
 * refusal (PRD §7.4/§7.5 — no published guidance covers the question). Pure, no-op if the last
 * message isn't an assistant turn (defensive; never happens given `send`'s own event order). */
function attachCitations(messages: ChatMessage[], citations: Citation[]): ChatMessage[] {
  const last = messages[messages.length - 1];
  if (last === undefined || last.role !== 'assistant') {
    return messages;
  }
  return [...messages.slice(0, -1), { ...last, citations, refusal: citations.length === 0 }];
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

  const send = useCallback((text: string) => {
    // Synchronous prefix: the user's turn and `streaming: true` both land before this function
    // returns (`useChatStream.test.ts`'s "streaming is true immediately after send()" pins this
    // — an async function's body runs synchronously up to its first `await`).
    setError(null);
    setMessages((prev) => [...prev, { role: 'user', text }]);
    setStreaming(true);

    let firstTokenSeen = false;

    void (async () => {
      try {
        const sessionId = readStoredSessionId();
        const payload: ChatRequest = { message: text, session_id: sessionId ?? undefined };
        const response = await fetch(`${resolveApiBaseUrl()}/api/v1/public/chat`, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify(payload),
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
        setError(GENERIC_ERROR_MESSAGE);
      } finally {
        setStreaming(false);
      }
    })();
  }, []);

  return { messages, streaming, error, send };
}
