import type { ConnectedAppDto } from '@/types/api/connectedApps';

// docs/plans/mcp-oauth/task-09-admin-connected-apps-ui.md — `ConnectedAppsTable` is dumb
// (docs/FRONTEND-CONVENTIONS.md §3): rows in, one click callback out. `onRevoke` opens the
// confirm dialog (owned by the screen/hook); the table never performs the delete itself.
// Fix round 1 (review I-1): moved from the parent screen's `interface.ts` into this component's
// own folder — FRONTEND-CONVENTIONS §3 folder-per-component (`ContentTable/interface.ts` is the
// pinned precedent), not the brief's flat-file path.
export interface ConnectedAppsTableProps {
  items: ConnectedAppDto[];
  onRevoke: (app: ConnectedAppDto) => void;
}
