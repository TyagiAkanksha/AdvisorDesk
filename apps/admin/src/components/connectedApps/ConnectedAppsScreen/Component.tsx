'use client';

import {
  Box,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  LoadingIndicator,
  Typography,
} from '@/components/common';

import { ConnectedAppsTable } from './components/ConnectedAppsTable';
import { useConnectedApps } from './useConnectedApps';

// docs/plans/mcp-oauth/task-09-admin-connected-apps-ui.md — dumb per
// docs/FRONTEND-CONVENTIONS.md §3: renders `useConnectedApps`' state, raises no logic of its own.
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

  if (isLoading && !hasData) {
    return <LoadingIndicator />;
  }

  if (isError && !hasData) {
    return <ErrorState message={errorMessage ?? undefined} />;
  }

  if (items.length === 0) {
    return (
      <EmptyState
        title="No connected apps"
        description="Apps that connect over MCP (like Claude) will appear here after you approve them."
      />
    );
  }

  return (
    <Box>
      <Typography variant="h2" component="h1">
        Connected apps
      </Typography>
      <ConnectedAppsTable items={items} onRevoke={requestRevoke} />
      <ConfirmDialog
        open={pendingRevoke !== null}
        title="Revoke access?"
        body={`${pendingRevoke?.client_name ?? ''} will lose MCP access immediately. It can reconnect later by authorizing again.`}
        confirmLabel="Revoke"
        onConfirm={confirmRevoke}
        onClose={cancelRevoke}
        isPending={isRevoking}
        errorMessage={revokeErrorMessage ?? undefined}
      />
    </Box>
  );
}
