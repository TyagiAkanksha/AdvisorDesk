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
}
