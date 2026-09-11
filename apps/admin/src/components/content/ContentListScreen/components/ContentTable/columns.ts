export interface ContentTableColumn {
  label: string;
  align?: 'right';
}

// p8 final, F13: one column definition shared by `ContentTable` (the loaded state) and
// `ContentTableSkeleton` (the loading state) so the header row and the skeleton's cell count can
// never drift apart — both map over this array instead of repeating the five `<TableCell>`s /
// a separately-maintained `COLUMN_COUNT`.
export const CONTENT_TABLE_COLUMNS: ContentTableColumn[] = [
  { label: 'Title' },
  { label: 'Status' },
  { label: 'Tags' },
  { label: 'Updated' },
  { label: 'Actions', align: 'right' as const },
];
