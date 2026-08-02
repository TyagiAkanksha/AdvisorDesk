// Frozen contract (defined by Component.test.tsx, task-06 Interfaces) — consumed unmodified by
// task-06's ContentEditorScreen. (The phase-5 agent panel renders its errors inline instead —
// owner-ratified 2026-08-02; a chat surface keeps failures visible in place.)
export interface AppSnackbarProps {
  open: boolean;
  message: string | null;
  /** @default 'error' */
  severity?: 'error' | 'success' | 'info' | 'warning';
  onClose: () => void;
}
