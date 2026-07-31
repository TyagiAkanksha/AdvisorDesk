import type { IconProps } from '../Icon';

export interface NavListItem {
  label: string;
  href: string;
  icon?: IconProps['name'];
}

/** A vertical list of `next/link`-driven nav items (docs/FRONTEND-CONVENTIONS.md
 * §4) — real anchor navigation, not client-side onClick routing. */
export interface NavListProps {
  items: NavListItem[];
}
