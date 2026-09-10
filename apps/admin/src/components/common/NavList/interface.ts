import type { IconProps } from '../Icon';

export interface NavListItem {
  label: string;
  href: string;
  icon?: IconProps['name'];
  /** The current route — rendered with MUI's `selected` state (phase-8 task-04, DESIGN.md §C1). */
  selected?: boolean;
}

/** A vertical list of `next/link`-driven nav items (docs/FRONTEND-CONVENTIONS.md
 * §4) — real anchor navigation, not client-side onClick routing. */
export interface NavListProps {
  items: NavListItem[];
  /** Fired after any item is clicked — a temporary drawer uses it to close itself
   * (phase-8 task-04, DESIGN.md §C1). */
  onNavigate?: () => void;
}
