import { useRisingEdgeNotice, useSnackbar } from '@/components/common';
import { useListContentQuery } from '@/lib/api/contentApi';
import { useGetStatsQuery } from '@/lib/api/statsApi';
import { DASHBOARD_REFRESH_ERROR } from '@/lib/copy';
import type { ContentDto } from '@/types/api/content';
import type { StatsDto } from '@/types/api/stats';

// task-17 (DESIGN.md §2, §5 C3): replaces useDashboardStats.ts — the dashboard now also reads
// `GET /api/v1/content` (recent content) and derives the tag table rows, so one hook owns both
// queries plus the background-refresh-failure snackbar.
export interface TagRow {
  tag: string;
  count: number;
}

export interface UseDashboardResult {
  stats: StatsDto | undefined;
  /** `stats.by_tag` as rows, sorted by count desc then tag asc. Empty while `stats` is undefined. */
  tagRows: TagRow[];
  recent: ContentDto[] | undefined;
  recentFailed: boolean;
  isLoading: boolean;
  loadFailed: boolean;
}

function toTagRows(byTag: Record<string, number> | undefined): TagRow[] {
  if (!byTag) {
    return [];
  }
  return Object.entries(byTag)
    .map(([tag, count]) => ({ tag, count }))
    .sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag));
}

export function useDashboard(): UseDashboardResult {
  const { data: stats, isLoading: statsIsLoading, isError: statsIsError } = useGetStatsQuery();
  const { data: recentList, isError: recentIsError } = useListContentQuery({
    page: 1,
    page_size: 5,
  });

  // Final review, finding F8/C-4 (propagated from useDashboardStats.ts): a background refetch
  // (e.g. another screen's mutation invalidating the `'Stats'` tag while this screen is still
  // mounted) failing must not blank the dashboard back to `ErrorState` — the last successfully
  // loaded counts stay visible, with the failure surfaced through the global snackbar instead.
  // Fired once per failure episode via `useRisingEdgeNotice` (no dismiss state needed — the
  // provider owns the notice's lifecycle).
  const { error: notifyError } = useSnackbar();
  const isBackgroundRefreshFailing = stats !== undefined && statsIsError;
  useRisingEdgeNotice(isBackgroundRefreshFailing, notifyError, DASHBOARD_REFRESH_ERROR);

  return {
    stats,
    tagRows: toTagRows(stats?.by_tag),
    recent: recentList?.items,
    recentFailed: recentList === undefined && recentIsError,
    isLoading: stats === undefined && statsIsLoading,
    loadFailed: stats === undefined && statsIsError,
  };
}
