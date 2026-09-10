import type { IconProps } from '../Icon';

export interface EmptyStateProps {
  message: string;
  /** Defaults to 'Article' (the existing look). */
  icon?: IconProps['name'];
  /** A way out of the empty state, rendered as an outlined link-button. */
  action?: { label: string; href: string };
}
