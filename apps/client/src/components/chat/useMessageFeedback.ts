import { useCallback, useRef, useState } from 'react';

import { sendMessageFeedback } from '@/lib/feedbackApi';
import { GENERIC_ERROR_MESSAGE } from '@/lib/copy';
import type { ChatFeedbackValue } from '@/types';

/**
 * Per-message 👍/👎 state (phase-9 DESIGN §A/D2): the only human ground truth in the loop. Flat,
 * colocated VM hook (docs/FRONTEND-CONVENTIONS.md §3) — keyed by `messageId`, not one global
 * "submitted" flag, since a transcript has many answers and any of them can be rated.
 *
 * **Why this state is not in `useChatStream`:** `messageId` belongs to the stream (it arrives on
 * the stream's own `done` event), but the optimistic value and its revert belong to the feedback
 * request. Putting them in `useChatStream` would make the stream hook import the feedback
 * endpoint and own a second network lifecycle — the tight coupling FRONTEND-CONVENTIONS §4
 * forbids. `ChatScreen` is the composition point that has both.
 */
export interface UseMessageFeedbackResult {
  /** What this message currently shows — optimistic while a request is in flight. */
  valueFor: (messageId: string) => ChatFeedbackValue | null;
  /** True while this message's request is in flight; both of its buttons disable. */
  pendingFor: (messageId: string) => boolean;
  /** Friendly copy for the last failed submission, or `null`. */
  error: string | null;
  /** Record 👍/👎 for one message. No-op while that message already has a request in flight. */
  select: (messageId: string, value: ChatFeedbackValue) => void;
}

export function useMessageFeedback(): UseMessageFeedbackResult {
  const [values, setValuesState] = useState<Record<string, ChatFeedbackValue | null>>({});
  const [pending, setPendingState] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);

  // Synchronous mirrors of `values`/`pending`, read inside `select` below — same rationale as
  // `useChatStream.ts`'s `streamingRef`: a plain state read inside a stable-identity `useCallback`
  // would close over whatever the state was on first render, not the current value. Updated in
  // lockstep with their state (inside the same setter below), never via a `useEffect` — so a read
  // immediately after a synchronous `select()` call is never one render behind.
  const valuesRef = useRef<Record<string, ChatFeedbackValue | null>>({});
  const setMessageValue = useCallback((messageId: string, value: ChatFeedbackValue | null) => {
    valuesRef.current = { ...valuesRef.current, [messageId]: value };
    setValuesState(valuesRef.current);
  }, []);

  const pendingRef = useRef<Record<string, boolean>>({});
  const setMessagePending = useCallback((messageId: string, value: boolean) => {
    pendingRef.current = { ...pendingRef.current, [messageId]: value };
    setPendingState(pendingRef.current);
  }, []);

  const valueFor = useCallback((messageId: string) => values[messageId] ?? null, [values]);
  const pendingFor = useCallback((messageId: string) => pending[messageId] ?? false, [pending]);

  const select = useCallback(
    (messageId: string, value: ChatFeedbackValue) => {
      // NOT rate-limited server-side (task 02), but a second click while the first request is
      // still in flight is a no-op here — one rating per message resolves at a time.
      if (pendingRef.current[messageId]) {
        return;
      }
      const previousValue = valuesRef.current[messageId] ?? null;

      setMessageValue(messageId, value);
      setMessagePending(messageId, true);

      void sendMessageFeedback(messageId, value)
        .then(() => {
          setError(null);
          setMessagePending(messageId, false);
        })
        .catch(() => {
          // 404 (pruned/unknown message id) and 422 (invalid value — shouldn't happen from this
          // UI, but the wire contract allows it) both land here: revert and stop, never retry.
          setMessageValue(messageId, previousValue);
          setError(GENERIC_ERROR_MESSAGE);
          setMessagePending(messageId, false);
        });
    },
    [setMessageValue, setMessagePending],
  );

  return { valueFor, pendingFor, error, select };
}
