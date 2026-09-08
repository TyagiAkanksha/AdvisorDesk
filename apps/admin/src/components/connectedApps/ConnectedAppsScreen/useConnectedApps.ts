import { useState } from 'react';

import {
  useGetConnectedAppsQuery,
  useRevokeConnectedAppMutation,
} from '@/lib/api/connectedAppsApi';
import { extractErrorMessage } from '@/lib/errorMessage';
import type { ConnectedAppDto } from '@/types/api/connectedApps';

// docs/plans/mcp-oauth/task-09-admin-connected-apps-ui.md: owns the list query + the confirm
// dialog's revoke flow so ConnectedAppsScreen stays dumb (docs/FRONTEND-CONVENTIONS.md §3).
// `hasData` is `true` once a page has ever loaded, so a LATER background refetch failure (e.g.
// another tab's revoke invalidating the `ConnectedApps` tag while this screen is still mounted)
// doesn't blank an already-rendered list back to a full-screen error — UNLIKE `useContentList`/
// `useDashboardStats`, this hook does not surface that background-failure case at all today (no
// Snackbar, no dismiss action): a background refetch failure here is currently silent (final
// fix round 1, F-5).
const REVOKE_ERROR_FALLBACK = "Couldn't revoke this app. Please try again.";
// Brief's Screen-behaviour section pins `isError && !hasData` -> `<ErrorState message=…>` to the
// PRD §9 envelope's own message where the failed response carries one (task-09 brief's
// Component.test.tsx: a 500 first load with `{"error":{"message":"boom"}}` must surface "boom",
// not a generic string) — this fallback only covers the rarer case of no envelope at all (e.g. a
// network error).
const LOAD_ERROR_FALLBACK = "Couldn't load connected apps.";

export interface UseConnectedAppsResult {
  items: ConnectedAppDto[];
  isLoading: boolean;
  isError: boolean;
  /** `true` once the list has loaded into `items` at least once (mirrors useContentList). */
  hasData: boolean;
  /** §9-friendly message for the first (non-cached) load's failure — `null` once `hasData`. */
  errorMessage: string | null;
  /** The app the confirm dialog is open for, else `null`. */
  pendingRevoke: ConnectedAppDto | null;
  requestRevoke: (app: ConnectedAppDto) => void;
  cancelRevoke: () => void;
  confirmRevoke: () => Promise<void>;
  isRevoking: boolean;
  revokeErrorMessage: string | null;
}

export function useConnectedApps(): UseConnectedAppsResult {
  const { data, error, isLoading, isError } = useGetConnectedAppsQuery();
  const hasData = data !== undefined;

  const [pendingRevoke, setPendingRevoke] = useState<ConnectedAppDto | null>(null);
  const [triggerRevoke, { isLoading: isRevoking }] = useRevokeConnectedAppMutation();
  const [revokeErrorMessage, setRevokeErrorMessage] = useState<string | null>(null);

  const requestRevoke = (app: ConnectedAppDto) => {
    setRevokeErrorMessage(null);
    setPendingRevoke(app);
  };

  const cancelRevoke = () => {
    setPendingRevoke(null);
    setRevokeErrorMessage(null);
  };

  const confirmRevoke = async () => {
    if (!pendingRevoke) {
      return;
    }
    try {
      await triggerRevoke(pendingRevoke.client_id).unwrap();
      setPendingRevoke(null);
      setRevokeErrorMessage(null);
    } catch (revokeError) {
      // Keep the dialog open (don't clear `pendingRevoke`) so the admin can read the message
      // and retry or cancel — mirrors useContentList's `deleteContent` failure handling.
      setRevokeErrorMessage(extractErrorMessage(revokeError, REVOKE_ERROR_FALLBACK));
    }
  };

  return {
    items: data?.items ?? [],
    isLoading,
    isError,
    hasData,
    errorMessage: !hasData && isError ? extractErrorMessage(error, LOAD_ERROR_FALLBACK) : null,
    pendingRevoke,
    requestRevoke,
    cancelRevoke,
    confirmRevoke,
    isRevoking,
    revokeErrorMessage,
  };
}
