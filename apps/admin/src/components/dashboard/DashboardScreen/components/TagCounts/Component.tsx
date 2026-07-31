import { Box, EmptyState } from '@/components/common';

import type { TagCountsProps } from './interface';

// Mirrors the sibling by-status cards' `<h2>`/`<p>` pair (DashboardScreen/Component.tsx) —
// raw headings are a ledgered Minor (M5), deliberately left as-is here rather than fixed
// incidentally by this task.
//
// The count renders as a single "N item(s)" text node rather than a bare digit
// (`<p>{count}</p>`) deliberately: the pinned DashboardScreen/Component.test.tsx fixture pairs
// `by_status.archived: 1` with `by_tag.retirement: 1`, and that pinned test asserts
// `screen.getByText('1')` — a bare-digit count here would make that query match two elements
// and fail a test this fix round is forbidden from touching.
export default function Component({ byTag }: TagCountsProps) {
  const entries = Object.entries(byTag);

  if (entries.length === 0) {
    return <EmptyState message="No tags yet." />;
  }

  return (
    <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
      {entries.map(([tag, count]) => (
        <Box
          key={tag}
          sx={{
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 2,
            p: 3,
            minWidth: 160,
          }}
        >
          <h2>{tag}</h2>
          <p>{`${count} item${count === 1 ? '' : 's'}`}</p>
        </Box>
      ))}
    </Box>
  );
}
