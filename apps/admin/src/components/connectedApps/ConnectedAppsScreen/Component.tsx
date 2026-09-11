'use client';

import { Box, ConfirmDialog, EmptyState, ErrorState, PageHeader } from '@/components/common';
import {
  CONNECTED_APPS_DESCRIPTION,
  CONNECTED_APPS_LOAD_ERROR,
  CONNECTED_APPS_TITLE,
  NO_CONNECTED_APPS_DESCRIPTION,
  NO_CONNECTED_APPS_TITLE,
  REVOKE_DIALOG_TITLE,
  REVOKE_LABEL,
} from '@/lib/copy';

import { ConnectedAppsSkeleton } from './components/ConnectedAppsSkeleton';
import { ConnectedAppsTable } from './components/ConnectedAppsTable';
import { useConnectedApps } from './useConnectedApps';

// docs/plans/mcp-oauth/task-09-admin-connected-apps-ui.md — dumb per
// docs/FRONTEND-CONVENTIONS.md §3: renders `useConnectedApps`' state, raises no logic of its own.
// phase-8 task-21 (DESIGN.md §2, §5 C6): the header renders in EVERY state (loading, error,
// empty, loaded) — mirrors ContentListScreen's PageHeader-always-visible structure (task-18).
export default function Component() {
  const {
    items,
    isLoading,
    isError,
    hasData,
    errorMessage,
    pendingRevoke,
    requestRevoke,
    cancelRevoke,
    confirmRevoke,
    isRevoking,
    revokeErrorMessage,
  } = useConnectedApps();

  return (
    <Box>
      <PageHeader title={CONNECTED_APPS_TITLE} description={CONNECTED_APPS_DESCRIPTION} />
      {isLoading && !hasData ? <ConnectedAppsSkeleton /> : null}
      {isError && !hasData ? (
        <ErrorState message={errorMessage ?? CONNECTED_APPS_LOAD_ERROR} />
      ) : null}
      {hasData && items.length === 0 ? (
        <EmptyState
          icon="Link"
          title={NO_CONNECTED_APPS_TITLE}
          description={NO_CONNECTED_APPS_DESCRIPTION}
        />
      ) : null}
      {hasData && items.length > 0 ? (
        <ConnectedAppsTable items={items} onRevoke={requestRevoke} />
      ) : null}
      <ConfirmDialog
        open={pendingRevoke !== null}
        title={REVOKE_DIALOG_TITLE}
        body={`${pendingRevoke?.client_name ?? ''} will lose MCP access immediately. It can reconnect later by authorizing again.`}
        confirmLabel={REVOKE_LABEL}
        onConfirm={confirmRevoke}
        onClose={cancelRevoke}
        isPending={isRevoking}
        errorMessage={revokeErrorMessage ?? undefined}
        destructive
      />
    </Box>
  );
}
