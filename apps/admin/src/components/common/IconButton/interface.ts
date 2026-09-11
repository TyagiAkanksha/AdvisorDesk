import type { IconProps } from '../Icon';

/**
 * An icon-only action button — the accessible name goes directly on the `<button>` via
 * `label` (docs/FRONTEND-CONVENTIONS.md §9: "icon-only buttons get `aria-label`"), not on the
 * decorative icon inside it.
 */
export interface IconButtonProps {
  name: IconProps['name'];
  /** Accessible name, e.g. "Delete Roth IRA Conversion Basics". */
  label: string;
  /** phase-8 task-14: optional now that `href` can also drive the button (a link needs no handler). */
  onClick?: () => void;
  size?: 'small' | 'medium' | 'large';
  disabled?: boolean;
  /** phase-8 task-14: internal (`/...`) renders via next/link; anything else, a plain `<a href>`. */
  href?: string;
  /** phase-8 task-14 (DESIGN.md §C1): `'inherit'` for buttons on the navy AppBar. */
  color?: 'default' | 'inherit' | 'primary' | 'error';
  /** phase-8 task-14: MUI's toolbar edge alignment — the AppBar menu button uses `'start'`. */
  edge?: 'start' | 'end';
  /** phase-8 task-14: shown on hover; `label` still owns the accessible name. */
  tooltip?: string;
}
