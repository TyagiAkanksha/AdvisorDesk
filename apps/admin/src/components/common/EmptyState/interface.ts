import type { ReactNode } from 'react';

import type { IconProps } from '../Icon';

// mcp-oauth task-09 (docs/plans/mcp-oauth/task-09-admin-connected-apps-ui.md): added the
// optional `title`/`description` two-line form for ConnectedAppsScreen's empty state, alongside
// the original single-`message` form every existing call site (ContentListScreen, TagCounts)
// still uses unchanged — at least one of `message` or `title` must be supplied by the caller.
export interface EmptyStateProps {
  message?: string;
  title?: string;
  description?: string;
  /** phase-8 task-14 (DESIGN.md §C4/§C7): overrides the default `'Article'` glyph. */
  icon?: IconProps['name'];
  /** phase-8 task-14: rendered under the text, e.g. a "New content" button. */
  action?: ReactNode;
}
