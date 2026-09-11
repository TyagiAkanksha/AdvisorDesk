import { Button, Select, Stack, TextField } from '@/components/common';
import { CLEAR_FILTERS_LABEL } from '@/lib/copy';
import { CONTENT_STATUS_LABELS, ContentStatus } from '@/types/api/content';

import type { ContentFiltersProps } from './interface';

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  ...Object.values(ContentStatus).map((status) => ({
    value: status,
    label: CONTENT_STATUS_LABELS[status],
  })),
];

// phase-8 task-18 (DESIGN.md §2, §5 C4): status/tag/search filters, plus a "Clear filters"
// button shown only once a filter is active. State lives one level up in `useContentList` (the
// URL) — this component only renders the current values and raises change events.
export default function Component({
  status,
  tag,
  q,
  tagOptions,
  hasFilters,
  onStatusChange,
  onTagChange,
  onQChange,
  onClear,
}: ContentFiltersProps) {
  return (
    <Stack
      direction={{ xs: 'column', sm: 'row' }}
      spacing={2}
      sx={{ mb: 3, alignItems: { sm: 'center' } }}
    >
      <Select
        label="Status"
        value={status}
        onChange={(value) => onStatusChange(value as ContentStatus | '')}
        options={STATUS_OPTIONS}
      />
      <Select label="Tag" value={tag} onChange={onTagChange} options={tagOptions} />
      <TextField
        label="Search"
        value={q}
        onChange={onQChange}
        placeholder="Search by title…"
        type="search"
      />
      {hasFilters ? (
        <Button variant="text" onClick={onClear}>
          {CLEAR_FILTERS_LABEL}
        </Button>
      ) : null}
    </Stack>
  );
}
