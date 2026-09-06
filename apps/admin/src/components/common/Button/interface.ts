import type { MouseEventHandler, ReactNode } from 'react';

/**
 * Button wraps `@mui/material/Button` behind a stable contract
 * (docs/FRONTEND-CONVENTIONS.md §4). Passing `href` without `onClick` renders
 * a real `<a>` (MUI's own ButtonBase behavior) — no JS-driven navigation.
 */
export interface ButtonProps {
  children: ReactNode;
  href?: string;
  onClick?: MouseEventHandler<HTMLElement>;
  variant?: 'text' | 'outlined' | 'contained';
  color?: 'primary' | 'secondary' | 'inherit';
  size?: 'small' | 'medium' | 'large';
  disabled?: boolean;
  fullWidth?: boolean;
  type?: 'button' | 'submit' | 'reset';
  // WR-13 (6R task-11): aria-* passthrough so disclosure buttons (menu/panel triggers) can
  // expose their expanded/popup state — this interface was closed before, blocking the fix.
  'aria-expanded'?: boolean;
  'aria-haspopup'?: boolean | 'true' | 'false' | 'menu' | 'listbox' | 'tree' | 'grid' | 'dialog';
  'aria-controls'?: string;
}
