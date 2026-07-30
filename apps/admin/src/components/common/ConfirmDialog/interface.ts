import type { ReactNode } from 'react';

// Base contract per task-05 Interfaces — reused by task-06 (editor) and phase-5 (agent panel).
// `errorMessage` added in fix round 1 (F2): a failed confirmed action (e.g. a DELETE 500) was
// silently swallowed by a bare `catch {}` with the dialog left open and zero feedback. Optional
// so every existing call site is unaffected until it opts in by populating it from the failed
// mutation's mapped error (`@/lib/errorMessage`'s `extractErrorMessage`).
export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  body: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  onClose: () => void;
  isPending: boolean;
  errorMessage?: string;
}
