import { useState } from 'react';

import { useRisingEdgeNotice, useSnackbar } from '@/components/common';
import {
  useGetConnectedAppsQuery,
  useRevokeConnectedAppMutation,
} from '@/lib/api/connectedAppsApi';
import {
  ACCESS_REVOKED_MESSAGE,
  CONNECTED_APPS_LOAD_ERROR,
  CONNECTED_APPS_REFRESH_ERROR,
  REVOKE_ERROR_FALLBACK,
} from '@/lib/copy';
import { extractErrorMessage } from '@/lib/errorMessage';
import type { ConnectedAppDto } from '@/types/api/connectedApps';

// docs/plans/mcp-oauth/task-09-admin-connected-apps-ui.md: owns the list query + the confirm
// dialog's revoke flow so ConnectedAppsScreen stays dumb (docs/FRONTEND-CONVENTIONS.md §3).
// `hasData` is `true` once a page has ever loaded, so a LATER background refetch failure (e.g.
// another tab's revoke invalidating the `ConnectedApps` tag while this screen is still mounted)
// doesn't blank an already-rendered list back to a full-screen error. phase-8 task-21 (DESIGN.md
// §2, §5 C6, closes F-5): that background-refetch failure now surfaces through the global
// snackbar, once per failure episode (rising edge of `hasData && isError`) — same idiom as
// `useContentList`/`useDashboard`. A successful revoke also raises a snackbar success notice.

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

  const { success: notifySuccess, error: notifyError } = useSnackbar();
  const isBackgroundRefreshFailing = hasData && isError;
  useRisingEdgeNotice(isBackgroundRefreshFailing, notifyError, CONNECTED_APPS_REFRESH_ERROR);

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
      notifySuccess(ACCESS_REVOKED_MESSAGE);
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
    errorMessage:
      !hasData && isError ? extractErrorMessage(error, CONNECTED_APPS_LOAD_ERROR) : null,
    pendingRevoke,
    requestRevoke,
    cancelRevoke,
    confirmRevoke,
    isRevoking,
    revokeErrorMessage,
  };
}
