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
  onClick: () => void;
  size?: 'small' | 'medium' | 'large';
  disabled?: boolean;
}
