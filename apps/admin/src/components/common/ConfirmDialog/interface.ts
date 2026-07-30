import type { ReactNode } from 'react';

// Exact contract per task-05 Interfaces — reused by task-06 (editor) and phase-5 (agent panel).
export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  body: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  onClose: () => void;
  isPending: boolean;
}
