// Frozen contract (defined by Component.test.tsx, task-06 Interfaces) — task-06's
// ContentEditorScreen and the phase-5 agent panel both consume this unmodified.
export interface AppSnackbarProps {
  open: boolean;
  message: string | null;
  /** @default 'error' */
  severity?: 'error' | 'success' | 'info' | 'warning';
  onClose: () => void;
}
