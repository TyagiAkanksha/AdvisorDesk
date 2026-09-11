import type { KeyboardEvent, Ref } from 'react';

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
  /**
   * Raw key events — the chat composer's Enter-to-send lives in its VM hook, not here.
   *
   * p8 t24: typed against the generic `HTMLElement`, not the input/textarea union — MUI's own
   * `TextField.onKeyDown` type is bound to its root element (`KeyboardEventHandler
   * <HTMLDivElement>`, even though the event genuinely originates on the inner input/textarea),
   * and `KeyboardEvent<HTMLDivElement>` is assignable to `KeyboardEvent<HTMLElement>` — so this
   * prop passes straight through to MUI with no cast.
   */
  onKeyDown?: (event: KeyboardEvent<HTMLElement>) => void;
  /**
   * fix round 1 (M-2): forwarded to MUI's own `inputRef` — the underlying <input>/<textarea> DOM
   * node, for imperative focus management (the chat composer refocuses the field once streaming
   * ends, and after "New conversation").
   */
  inputRef?: Ref<HTMLInputElement | HTMLTextAreaElement>;
}
