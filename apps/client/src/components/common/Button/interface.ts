import type { MouseEventHandler, ReactNode } from 'react';

// task-05 (phase-4): the client app's first interactive-action primitive (send/submit) —
// FRONTEND-CONVENTIONS.md §4 "grow common/ on demand". Mirrors
// apps/admin/src/components/common/Button/interface.ts's shape, minus the `href` anchor-mode
// half (no client screen needs a link-styled-as-a-button yet; `common/Link` already covers real
// navigation) — kept intentionally smaller than admin's until a real caller needs more.
export interface ButtonProps {
  children: ReactNode;
  onClick?: MouseEventHandler<HTMLElement>;
  type?: 'button' | 'submit' | 'reset';
  variant?: 'text' | 'outlined' | 'contained';
  disabled?: boolean;
}
