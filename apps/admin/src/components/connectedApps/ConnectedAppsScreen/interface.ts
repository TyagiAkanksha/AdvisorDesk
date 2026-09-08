import type { ConnectedAppDto } from '@/types/api/connectedApps';

// docs/plans/mcp-oauth/task-09-admin-connected-apps-ui.md — `ConnectedAppsTable` is dumb
// (docs/FRONTEND-CONVENTIONS.md §3): rows in, one click callback out. `onRevoke` opens the
// confirm dialog (owned by the screen/hook); the table never performs the delete itself.
export interface ConnectedAppsTableProps {
  items: ConnectedAppDto[];
  onRevoke: (app: ConnectedAppDto) => void;
}
