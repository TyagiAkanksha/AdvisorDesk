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
  onKeyDown: (event: KeyboardEvent<HTMLElement>) => void;
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

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    // fix round 1, M-1: while an IME composition is in progress (e.g. confirming a kanji
    // candidate), the browser's own "confirm" Enter must reach the input un-intercepted — we
    // neither preventDefault nor submit on it, exactly as if it weren't an Enter press at all.
    // `nativeEvent` is optional-chained: the authored unit tests' `key()` fixture builds a plain
    // object with no `nativeEvent` at all (a real DOM KeyboardEvent always has one).
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent?.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  return { draft, setDraft, canSend, submit, onKeyDown };
}
