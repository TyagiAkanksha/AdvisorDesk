'use client';

import { Box, ErrorState, LoadingIndicator } from '@/components/common';
import { useGetStatsQuery } from '@/lib/api/statsApi';
import { CONTENT_STATUS_LABELS, ContentStatus } from '@/types/api/content';

// task-05 / PRD §2.2: one card per content status, always shown in this fixed order —
// `by_status` (a plain string-keyed dict from the API) may omit a status with a zero count.
const STATUSES = Object.values(ContentStatus);

export default function Component() {
  const { data, isLoading, isError } = useGetStatsQuery();

  if (isLoading) {
    return <LoadingIndicator />;
  }

  if (isError || !data) {
    return <ErrorState message="Couldn't load the dashboard stats." />;
  }

  return (
    <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
      {STATUSES.map((status) => (
        <Box
          key={status}
          sx={{
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 2,
            p: 3,
            minWidth: 160,
          }}
        >
          <h2>{CONTENT_STATUS_LABELS[status]}</h2>
          <p>{data.by_status[status] ?? 0}</p>
        </Box>
      ))}
    </Box>
  );
}
