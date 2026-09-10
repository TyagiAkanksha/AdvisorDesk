import type { KeyboardEvent } from 'react';

// phase-8 task-12 (DESIGN.md §B4). Dumb leaf — every rule (send-gating, the Enter/Shift+Enter
// keyboard rule, the draft itself) lives in `../useChatComposer`; this component only renders.
export interface ChatComposerProps {
  draft: string;
  onDraftChange: (value: string) => void;
  onSubmit: () => void;
  onKeyDown: (event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => void;
  canSend: boolean;
  /** true while the assistant's answer is streaming. */
  streaming: boolean;
  onStop: () => void;
  onNewConversation: () => void;
  /** messages.length > 0 */
  showNewConversation: boolean;
}
