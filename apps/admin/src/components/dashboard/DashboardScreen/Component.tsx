'use client';

import {
  Box,
  ErrorState,
  Grid,
  PageHeader,
  Paper,
  Skeleton,
  StatCard,
  Typography,
} from '@/components/common';
import {
  CONTENT_BY_TAG_TITLE,
  DASHBOARD_LOAD_ERROR,
  DASHBOARD_TITLE,
  RECENT_CONTENT_LOAD_ERROR,
  RECENT_CONTENT_TITLE,
  WEAK_QUERIES_LOAD_ERROR,
  WEAK_QUERIES_TITLE,
} from '@/lib/copy';
import { CONTENT_STATUS_LABELS, ContentStatus } from '@/types/api/content';

import { DashboardSkeleton } from './components/DashboardSkeleton';
import { RecentContent } from './components/RecentContent';
import { TagTable } from './components/TagTable';
import { WeakQueries } from './components/WeakQueries';
import { useDashboard } from './useDashboard';

// task-05 / PRD §2.2: one card per content status, always shown in this fixed order —
// `by_status` (a plain string-keyed dict from the API) may omit a status with a zero count.
const STATUSES = Object.values(ContentStatus);

// task-17 (DESIGN.md §2, §5 C3): PageHeader + three linked StatCards (Draft/Published/Archived
// → the filtered content list) and two outlined panels — Content by tag, Recent content.
export default function Component() {
  const {
    stats,
    tagRows,
    recent,
    recentFailed,
    weakQueries,
    weakQueriesFailed,
    isLoading,
    loadFailed,
  } = useDashboard();

  // p8 final, F5: the header now renders in EVERY state (loading/error/loaded) — mirrors
  // ContentListScreen/ConnectedAppsScreen's PageHeader-always-visible structure (tasks 18/21) —
  // instead of disappearing behind the early-return skeleton/error branches.
  return (
    <Box>
      <PageHeader title={DASHBOARD_TITLE} />
      {isLoading ? <DashboardSkeleton /> : null}
      {/* Final review, finding F8/C-4: `ErrorState` only replaces the dashboard when there is
          genuinely nothing cached to show — a background refetch failure with stats still cached
          surfaces through the global snackbar instead (useDashboard.ts). */}
      {!isLoading && (loadFailed || !stats) ? <ErrorState message={DASHBOARD_LOAD_ERROR} /> : null}
      {!isLoading && !loadFailed && stats ? (
        <Grid container spacing={2}>
          {STATUSES.map((status) => (
            <Grid key={status} size={{ xs: 12, sm: 4 }}>
              <StatCard
                label={CONTENT_STATUS_LABELS[status]}
                value={stats.by_status[status] ?? 0}
                href={`/content?status=${status}`}
              />
            </Grid>
          ))}
          <Grid size={{ xs: 12, md: 6 }}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="h5" component="h2" sx={{ mb: 1.5 }}>
                {CONTENT_BY_TAG_TITLE}
              </Typography>
              <TagTable rows={tagRows} />
            </Paper>
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="h5" component="h2" sx={{ mb: 1.5 }}>
                {RECENT_CONTENT_TITLE}
              </Typography>
              {recentFailed ? <ErrorState message={RECENT_CONTENT_LOAD_ERROR} /> : null}
              {recent ? <RecentContent items={recent} /> : null}
              {!recent && !recentFailed ? <Skeleton variant="rectangular" height={160} /> : null}
            </Paper>
          </Grid>
          <Grid size={{ xs: 12 }}>
            <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
              <Typography variant="h5" component="h2" sx={{ mb: 1.5 }}>
                {WEAK_QUERIES_TITLE}
              </Typography>
              {weakQueriesFailed ? <ErrorState message={WEAK_QUERIES_LOAD_ERROR} /> : null}
              {weakQueries ? <WeakQueries items={weakQueries} /> : null}
              {!weakQueries && !weakQueriesFailed ? (
                <Skeleton variant="rectangular" height={160} />
              ) : null}
            </Paper>
          </Grid>
        </Grid>
      ) : null}
    </Box>
  );
}
