import type { IconProps } from '../Icon';

/**
 * An icon-only action button — the accessible name goes directly on the `<button>` via
 * `label` (docs/FRONTEND-CONVENTIONS.md §9: "icon-only buttons get `aria-label`"), not on the
 * decorative icon inside it. Mirrors apps/admin/src/components/common/IconButton, plus `type`
 * (chat composer's send button needs `type="submit"`) and `color` (phase-8 task-06).
 */
export interface IconButtonProps {
  name: IconProps['name'];
  /** Accessible name — goes on the <button>, not the icon (FRONTEND-CONVENTIONS §9). */
  label: string;
  onClick?: () => void;
  type?: 'button' | 'submit';
  size?: 'small' | 'medium' | 'large';
  color?: 'default' | 'primary';
  disabled?: boolean;
  /** Toggle state for a button that represents an on/off choice — renders `aria-pressed`
   * (FRONTEND-CONVENTIONS.md §9: an assistive-tech user must be able to tell which thumb is
   * chosen). Omit for a plain action button. */
  pressed?: boolean;
}
