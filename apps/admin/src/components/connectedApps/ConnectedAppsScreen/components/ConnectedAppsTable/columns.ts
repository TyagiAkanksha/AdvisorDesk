export interface ConnectedAppsTableColumn {
  label: string;
  align?: 'right';
}

// p8 final, F13: one column definition shared by `ConnectedAppsTable` (the loaded state) and
// `ConnectedAppsSkeleton` (the loading state) so the header row and the skeleton's cell count
// can never drift apart — mirrors `ContentTable`'s own `columns.ts`.
export const CONNECTED_APPS_TABLE_COLUMNS: ConnectedAppsTableColumn[] = [
  { label: 'Client' },
  { label: 'Connected' },
  { label: 'Last used' },
  { label: 'Actions', align: 'right' as const },
];
