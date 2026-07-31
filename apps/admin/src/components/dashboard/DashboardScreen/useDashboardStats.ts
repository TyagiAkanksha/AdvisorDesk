import { useState } from 'react';

import { useGetStatsQuery } from '@/lib/api/statsApi';
import type { StatsDto } from '@/types/api/stats';

// Final review, finding F8/C-4: propagates task-06 fix round 1 F3's resilience pattern
// (ContentEditorScreen/useContentEditor.ts's `hasContent`/background-refetch-alert shape) to
// the dashboard — a background refetch (e.g. the `'Stats'`-tag invalidation any content
// publish/archive/delete elsewhere in the app triggers while this screen is still mounted)
// failing must not blank the dashboard back to `ErrorState`; the last successfully loaded
// counts should stay visible, with the failure surfaced as a dismissible banner instead.
const REFRESH_ERROR_FALLBACK = "Couldn't refresh the dashboard — showing the last loaded data.";

export interface UseDashboardStatsResult {
  data: StatsDto | undefined;
  isLoading: boolean;
  isError: boolean;
  /** §9-friendly message for a background refetch failure with data still cached, else `null`. */
  refreshErrorMessage: string | null;
  /** Dismisses the current `refreshErrorMessage` — a later, distinct failure gets its own. */
  dismissRefreshError: () => void;
}

export function useDashboardStats(): UseDashboardStatsResult {
  const { data, isLoading, isError } = useGetStatsQuery();

  // Same idiom as useContentEditor's `refreshErrorDismissed` (fix round 2, N2): reset the
  // dismissal once `isError` clears, so a later, distinct failure gets its own alert rather
  // than staying silenced by an earlier dismissal.
  const [dismissed, setDismissed] = useState(false);
  if (!isError && dismissed) {
    setDismissed(false);
  }

  const backgroundRefetchFailed = data !== undefined && isError && !dismissed;

  return {
    data,
    isLoading,
    isError,
    refreshErrorMessage: backgroundRefetchFailed ? REFRESH_ERROR_FALLBACK : null,
    dismissRefreshError: () => setDismissed(true),
  };
}
