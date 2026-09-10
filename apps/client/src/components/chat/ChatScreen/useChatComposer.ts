import type { KeyboardEvent } from 'react';
import { useState } from 'react';

// phase-8 task-12 (DESIGN.md §B4). VM hook for the chat composer (docs/FRONTEND-CONVENTIONS.md
// §3: "VM hooks are flat and colocated... Args/Result declared in-file") — the draft string, the
// send-gating rule, and the Enter/Shift+Enter keyboard rule all live here so `ChatComposer` stays
// a dumb leaf.
export interface UseChatComposerArgs {
  /** true while streaming — a send while the previous answer is still in flight is a no-op. */
  disabled: boolean;
  onSend: (text: string) => void;
}

export interface UseChatComposerResult {
  draft: string;
  setDraft: (value: string) => void;
  /** draft.trim().length > 0 && !disabled */
  canSend: boolean;
  /** Trims the draft, sends it if `canSend`, then clears the draft. No-op otherwise. */
  submit: () => void;
  /** Enter -> preventDefault + submit; Shift+Enter -> left to the field (inserts a newline). */
  onKeyDown: (event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => void;
}

export function useChatComposer({ disabled, onSend }: UseChatComposerArgs): UseChatComposerResult {
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
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  return { draft, setDraft, canSend, submit, onKeyDown };
}
