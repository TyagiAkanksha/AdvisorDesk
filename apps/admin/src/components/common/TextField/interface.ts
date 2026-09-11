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
  /**
   * Raw key events, e.g. Enter-to-send in a chat composer.
   *
   * p8 t24: typed against the generic `HTMLElement`, not the input/textarea union — MUI's own
   * `TextField.onKeyDown` type is bound to its root element (`KeyboardEventHandler
   * <HTMLDivElement>`, even though the event genuinely originates on the inner input/textarea),
   * and `KeyboardEvent<HTMLDivElement>` is assignable to `KeyboardEvent<HTMLElement>` — so this
   * prop passes straight through to MUI with no cast.
   */
  onKeyDown?: (event: KeyboardEvent<HTMLElement>) => void;
  /** phase-8 task-14 (DESIGN.md §C5): the editor's Body field renders in a monospace font. */
  monospace?: boolean;
}
