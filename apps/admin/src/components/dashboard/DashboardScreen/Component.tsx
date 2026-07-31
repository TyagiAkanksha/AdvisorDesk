'use client';

import { AppSnackbar, Box, ErrorState, LoadingIndicator } from '@/components/common';
import { CONTENT_STATUS_LABELS, ContentStatus } from '@/types/api/content';

import { TagCounts } from './components/TagCounts';
import { useDashboardStats } from './useDashboardStats';

// task-05 / PRD §2.2: one card per content status, always shown in this fixed order —
// `by_status` (a plain string-keyed dict from the API) may omit a status with a zero count.
const STATUSES = Object.values(ContentStatus);

export default function Component() {
  const { data, isLoading, refreshErrorMessage, dismissRefreshError } = useDashboardStats();

  if (isLoading && !data) {
    return <LoadingIndicator />;
  }

  // Final review, finding F8/C-4: `isError` alone used to blank the whole dashboard back to
  // `ErrorState` even when `data` was still cached from an earlier successful load — a
  // background refetch failure (e.g. another screen's mutation invalidating the `'Stats'` tag
  // while this one is still mounted) looked identical to never having loaded anything at all.
  // `ErrorState` now only replaces the dashboard when there is genuinely nothing cached to show.
  if (!data) {
    return <ErrorState message="Couldn't load the dashboard stats." />;
  }

  return (
    <Box>
      <AppSnackbar
        open={refreshErrorMessage !== null}
        message={refreshErrorMessage}
        severity="warning"
        onClose={dismissRefreshError}
      />
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
      {/* fix round 1, F3: the brief's Goal calls for "status/tag counts from GET /stats" —
          `by_tag` was never rendered. */}
      <Box sx={{ mt: 3 }}>
        <TagCounts byTag={data.by_tag} />
      </Box>
    </Box>
  );
}
