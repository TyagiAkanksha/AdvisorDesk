// mcp-oauth task-09 (docs/plans/mcp-oauth/task-09-admin-connected-apps-ui.md): added the
// optional `title`/`description` two-line form for ConnectedAppsScreen's empty state, alongside
// the original single-`message` form every existing call site (ContentListScreen, TagCounts)
// still uses unchanged — at least one of `message` or `title` must be supplied by the caller.
export interface EmptyStateProps {
  message?: string;
  title?: string;
  description?: string;
}
