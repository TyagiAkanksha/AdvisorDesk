import type { MouseEventHandler, ReactNode } from 'react';

// task-05 (phase-4): the client app's first interactive-action primitive (send/submit) —
// FRONTEND-CONVENTIONS.md §4 "grow common/ on demand". Mirrors
// apps/admin/src/components/common/Button/interface.ts's shape.
//
// phase-8 task-06: `href`/`color`/`size`/`startIcon`/`fullWidth` added — the shell/home/article
// screens need a link-styled-as-a-button (e.g. EmptyState's "Show all" action, ErrorState's
// "Try again" retry). Internal (`/...`) hrefs render via next/link; external hrefs render a
// plain `<a>` (same split as apps/admin/src/components/common/Button/Component.tsx).
export interface ButtonProps {
  children: ReactNode;
  /** Internal (`/...`) renders via next/link; external renders a plain <a>. */
  href?: string;
  onClick?: MouseEventHandler<HTMLElement>;
  type?: 'button' | 'submit' | 'reset';
  variant?: 'text' | 'outlined' | 'contained';
  color?: 'primary' | 'secondary' | 'inherit' | 'error';
  size?: 'small' | 'medium' | 'large';
  startIcon?: ReactNode;
  fullWidth?: boolean;
  disabled?: boolean;
}
