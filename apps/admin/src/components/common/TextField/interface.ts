import type { KeyboardEvent } from 'react';

/** A labeled, generic text input (docs/FRONTEND-CONVENTIONS.md §4). */
export interface TextFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  size?: 'small' | 'medium';
  fullWidth?: boolean;
  type?: 'text' | 'search';
  /** task-06: multi-line growth for longer inputs (e.g. the editor's markdown body). */
  multiline?: boolean;
  minRows?: number;
  /** phase-8 task-04: caps growth for `multiline` fields (e.g. a chat composer). */
  maxRows?: number;
  /** phase-5 task-04: disables the field, e.g. `AgentPanel`'s message box while streaming. */
  disabled?: boolean;
  /** phase-8 task-04: marks the field required (DESIGN.md §C5). */
  required?: boolean;
  /** Validation state — pairs with `helperText` (phase-8 task-04, DESIGN.md §C5). */
  error?: boolean;
  helperText?: string;
  onBlur?: () => void;
  /** Raw key events, e.g. Enter-to-send in a chat composer. */
  onKeyDown?: (event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => void;
}
