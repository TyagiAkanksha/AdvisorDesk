import type { SxProps, Theme } from '@mui/material/styles';
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
  // 'error' added phase-8 task-04 (DESIGN.md §2: error colour = destructive) so ConfirmDialog
  // can render a destructive confirm button through this same primitive.
  color?: 'primary' | 'secondary' | 'inherit' | 'error';
  size?: 'small' | 'medium' | 'large';
  disabled?: boolean;
  fullWidth?: boolean;
  type?: 'button' | 'submit' | 'reset';
  // phase-8 task-04: an optional leading icon (e.g. ErrorState's "Retry" action).
  startIcon?: ReactNode;
  // WR-13 (6R task-11): aria-* passthrough so disclosure buttons (menu/panel triggers) can
  // expose their expanded/popup state — this interface was closed before, blocking the fix.
  'aria-expanded'?: boolean;
  'aria-haspopup'?: boolean | 'true' | 'false' | 'menu' | 'listbox' | 'tree' | 'grid' | 'dialog';
  'aria-controls'?: string;
  // mcp-oauth task-09: same passthrough precedent as the three aria-* props above — the
  // ConnectedAppsTable's per-row "Revoke" button needs an accessible name distinct from its
  // visible label ("Revoke <client_name>", docs/plans/mcp-oauth/task-09-admin-connected-apps-ui.md).
  'aria-label'?: string;
  // phase-8 task-23: the agent panel's tool-card toggle needs left-aligned monospace text — an
  // escape hatch straight through to MuiButton, admin-only (no client call site needs it yet).
  sx?: SxProps<Theme>;
}
