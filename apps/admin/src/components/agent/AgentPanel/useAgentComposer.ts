import type { KeyboardEvent } from 'react';
import { useState } from 'react';

// phase-8 task-23 (DESIGN.md §5 C7). Colocated VM hook for the agent panel's composer — same
// contract as apps/client's `useChatComposer.ts` (read-only reference, not imported): the draft
// string, the send-gating rule, and the Enter/Shift+Enter keyboard rule all live here so
// `AgentComposer` stays a dumb leaf.
export interface UseAgentComposerArgs {
  /** true while streaming — a send while the previous answer is still in flight is a no-op. */
  disabled: boolean;
  onSend: (text: string) => void;
}

export interface UseAgentComposerResult {
  draft: string;
  setDraft: (value: string) => void;
  /** draft.trim().length > 0 && !disabled */
  canSend: boolean;
  /** Trims the draft, sends it if `canSend`, then clears the draft. No-op otherwise. */
  submit: () => void;
  /** Enter -> preventDefault + submit; Shift+Enter -> left to the field (inserts a newline). */
  onKeyDown: (event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => void;
}

export function useAgentComposer({
  disabled,
  onSend,
}: UseAgentComposerArgs): UseAgentComposerResult {
  const [draft, setDraft] = useState('');
  const canSend = draft.trim().length > 0 && !disabled;

  const submit = () => {
    if (!canSend) {
      return;
    }
    onSend(draft.trim());
    setDraft('');
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    // Mirrors `useChatComposer.ts`'s M-1: while an IME composition is in progress, the browser's
    // own "confirm" Enter must reach the input un-intercepted.
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent?.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  return { draft, setDraft, canSend, submit, onKeyDown };
}
