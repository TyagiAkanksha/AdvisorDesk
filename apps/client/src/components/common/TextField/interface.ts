// task-05 (phase-4): the client app's first labeled-text-input primitive (the chat message
// field) — FRONTEND-CONVENTIONS.md §4 "grow common/ on demand". Mirrors
// apps/admin/src/components/common/TextField/interface.ts's controlled-input shape, trimmed to
// what ChatScreen actually needs (no `multiline`/`type`/`size` variants yet — add them when a
// real caller needs them, same trade-off as `common/Button`).
export interface TextFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  fullWidth?: boolean;
}
