import type { KeyboardEvent } from 'react';

// task-05 (phase-4): the client app's first labeled-text-input primitive (the chat message
// field) — FRONTEND-CONVENTIONS.md §4 "grow common/ on demand". Mirrors
// apps/admin/src/components/common/TextField/interface.ts's controlled-input shape.
//
// phase-8 task-06: `multiline`/`minRows`/`maxRows`/`onKeyDown` added for the chat composer's
// growing textarea and Enter-to-send handling.
export interface TextFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  fullWidth?: boolean;
  multiline?: boolean;
  minRows?: number;
  maxRows?: number;
  /** Raw key events — the chat composer's Enter-to-send lives in its VM hook, not here. */
  onKeyDown?: (event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => void;
}
