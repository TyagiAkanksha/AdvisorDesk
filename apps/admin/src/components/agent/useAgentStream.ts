import { useCallback, useEffect, useRef, useState } from 'react';

import { invalidateAgentWrites } from '@/lib/api/contentApi';
import { API_BASE_URL } from '@/lib/apiBase';
import { useAppDispatch } from '@/lib/hooks';
import { parseSseStream } from '@/lib/parseSseStream';

// phase-5 task-04, PRD §2.2, §5.4; docs/FRONTEND-CONVENTIONS.md §6. Colocated VM hook
// (`useChatStream.ts`'s own precedent, lifted per the task brief) for `AgentPanel`. Posts to
// `POST /api/v1/agent/chat`, stateless on the server (§5.4): the FULL conversation lives in this
// hook's own `turns` state and is resent whole on every `send()` — there is no session id to
// round-trip, unlike the client chat's `localStorage` session.

/** One tool call/result rendered inline with the assistant turn that produced it, in stream
 * order (§5.4: "tool events interleaved with tokens in execution order"). */
export interface ToolEvent {
  kind: 'call' | 'result';
  tool: string;
  /** `'call'`: compact `JSON.stringify(arguments)`. `'result'`: `result_summary` verbatim. */
  detail: string;
}

/** One turn in the conversation — `AgentPanel`'s render list, `AgentMessage`'s prop. */
export interface AgentTurn {
  role: 'user' | 'assistant';
  text: string;
  events: ToolEvent[];
}

export interface UseAgentStreamResult {
  turns: AgentTurn[];
  streaming: boolean;
  error: string | null;
  send: (text: string) => void;
}

const NETWORK_ERROR_MESSAGE = "Couldn't reach the agent. Please try again.";
const GENERIC_STREAM_ERROR_MESSAGE = 'The agent failed to complete this request. Please try again.';

/** Append a `token` chunk to the in-progress assistant turn, starting a new one if the last
 * turn isn't an in-progress assistant turn yet (mirrors `useChatStream.ts`'s
 * `appendAssistantToken` — the newest turn is always the just-added user turn until the first
 * `token`/`tool_call`/`tool_result` of the response arrives). Pure. */
function appendAssistantToken(turns: AgentTurn[], chunk: string): AgentTurn[] {
  const last = turns[turns.length - 1];
  if (last === undefined || last.role !== 'assistant') {
    return [...turns, { role: 'assistant', text: chunk, events: [] }];
  }
  return [...turns.slice(0, -1), { ...last, text: last.text + chunk }];
}

/** Append a `ToolEvent` to the in-progress assistant turn's `events` list, in arrival order —
 * same "start a new assistant turn if needed" rule as `appendAssistantToken`. Pure. */
function appendAssistantEvent(turns: AgentTurn[], event: ToolEvent): AgentTurn[] {
  const last = turns[turns.length - 1];
  if (last === undefined || last.role !== 'assistant') {
    return [...turns, { role: 'assistant', text: '', events: [event] }];
  }
  return [...turns.slice(0, -1), { ...last, events: [...last.events, event] }];
}

/** Turn a non-2xx `/agent/chat` response into a friendly, never-raw-JSON message (PRD §9's
 * envelope's own `.message` is already human-authored copy). Falls back to the generic message
 * if the body isn't the expected envelope shape. */
async function friendlyErrorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { error?: { message?: string } };
    if (body.error?.message) {
      return body.error.message;
    }
  } catch {
    // Unparsable body — fall through to the generic message below.
  }
  return GENERIC_STREAM_ERROR_MESSAGE;
}

/**
 * The admin agent panel's VM hook (PRD §2.2, §5.4). Posts the full resent history to
 * `POST /api/v1/agent/chat` (admin-cookie-gated: `credentials: 'include'`), streams the typed
 * SSE events into `turns`/`streaming`/`error`, and dispatches `Content`/`Stats`/`Tags`
 * invalidation on every `done` so open screens refetch agent writes without a manual reload.
 */
export function useAgentStream(): UseAgentStreamResult {
  const dispatch = useAppDispatch();
  const [turns, setTurns] = useState<AgentTurn[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Ref mirrors of `streaming`/`turns`, read synchronously at the top of `send()` — a plain
  // state read inside the stable `useCallback([])` body would close over a stale value (same
  // pattern as `useChatStream.ts`'s `streamingRef`). `turnsRef` is what makes the §5.4 "resend
  // full history" resend the CURRENT history rather than whatever `turns` was on first render.
  const streamingRef = useRef(false);
  const turnsRef = useRef<AgentTurn[]>([]);

  const setStreamingState = useCallback((value: boolean) => {
    streamingRef.current = value;
    setStreaming(value);
  }, []);

  const setTurnsState = useCallback((updater: (prev: AgentTurn[]) => AgentTurn[]) => {
    setTurns((prev) => {
      const next = updater(prev);
      turnsRef.current = next;
      return next;
    });
  }, []);

  // Abort the in-flight request on unmount — a component that isn't mounted anymore shouldn't
  // keep updating state for it (mirrors `useChatStream.ts`'s M-5).
  const abortControllerRef = useRef<AbortController | null>(null);
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const send = useCallback(
    (text: string) => {
      // Re-entrancy guard: a second concurrent `send()` while one is already streaming is a
      // no-op (belt-and-suspenders on top of `AgentPanel` disabling its own controls).
      if (streamingRef.current) {
        return;
      }

      const priorHistory = turnsRef.current.map((turn) => ({
        role: turn.role,
        content: turn.text,
      }));

      setError(null);
      setTurnsState((prev) => [...prev, { role: 'user', text, events: [] }]);
      setStreamingState(true);

      const controller = new AbortController();
      abortControllerRef.current = controller;

      void (async () => {
        try {
          const response = await fetch(`${API_BASE_URL}/api/v1/agent/chat`, {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
              messages: [...priorHistory, { role: 'user', content: text }],
            }),
            signal: controller.signal,
          });

          if (!response.ok) {
            setError(await friendlyErrorMessage(response));
            return;
          }

          const body = response.body;
          if (body === null) {
            setError(GENERIC_STREAM_ERROR_MESSAGE);
            return;
          }

          await parseSseStream(body.getReader(), {
            onToken: (chunk) => {
              setTurnsState((prev) => appendAssistantToken(prev, chunk));
            },
            onToolCall: ({ tool, arguments: args }) => {
              setTurnsState((prev) =>
                appendAssistantEvent(prev, { kind: 'call', tool, detail: JSON.stringify(args) }),
              );
            },
            onToolResult: ({ tool, result_summary }) => {
              setTurnsState((prev) =>
                appendAssistantEvent(prev, { kind: 'result', tool, detail: result_summary }),
              );
            },
            onDone: () => {
              dispatch(invalidateAgentWrites());
            },
            onError: ({ message }) => {
              setError(message);
            },
          });
        } catch {
          if (!controller.signal.aborted) {
            setError(NETWORK_ERROR_MESSAGE);
          }
        } finally {
          if (abortControllerRef.current === controller) {
            abortControllerRef.current = null;
          }
          setStreamingState(false);
        }
      })();
    },
    [dispatch, setStreamingState, setTurnsState],
  );

  return { turns, streaming, error, send };
}
