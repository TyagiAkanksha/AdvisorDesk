import { Box, Button } from '@/components/common';

import type { ConnectedAppsTableProps } from './interface';

// docs/plans/mcp-oauth/task-09-admin-connected-apps-ui.md — dumb per
// docs/FRONTEND-CONVENTIONS.md §3 (rows in, one click callback out); mirrors ContentTable's
// `Box component="table"` pattern (content/ContentListScreen/components/ContentTable/Component.tsx).
function formatDate(iso: string | null): string {
  return iso === null ? '—' : new Date(iso).toLocaleString();
}

export default function Component({ items, onRevoke }: ConnectedAppsTableProps) {
  return (
    <Box component="table" sx={{ width: '100%', borderCollapse: 'collapse' }}>
      <Box component="thead">
        <Box component="tr">
          <Box component="th" sx={{ textAlign: 'left', p: 1 }}>
            App
          </Box>
          <Box component="th" sx={{ textAlign: 'left', p: 1 }}>
            Approved
          </Box>
          <Box component="th" sx={{ textAlign: 'left', p: 1 }}>
            Access tokens
          </Box>
          <Box component="th" sx={{ textAlign: 'left', p: 1 }}>
            Refresh tokens
          </Box>
          <Box component="th" sx={{ textAlign: 'left', p: 1 }}>
            Last used
          </Box>
          <Box component="th" sx={{ textAlign: 'left', p: 1 }}>
            Expires
          </Box>
          {/* Unlabeled actions column, per the brief's Screen-behaviour section. */}
          <Box component="th" sx={{ p: 1 }} />
        </Box>
      </Box>
      <Box component="tbody">
        {items.map((item) => (
          <Box
            component="tr"
            key={item.client_id}
            data-testid={`connected-app-${item.client_id}`}
            sx={{ borderTop: '1px solid', borderColor: 'divider' }}
          >
            <Box component="td" sx={{ p: 1 }}>
              {item.client_name}
            </Box>
            <Box component="td" sx={{ p: 1 }}>
              {formatDate(item.consent_granted_at)}
            </Box>
            <Box component="td" sx={{ p: 1 }}>
              {item.active_access_tokens}
            </Box>
            <Box component="td" sx={{ p: 1 }}>
              {item.active_refresh_tokens}
            </Box>
            <Box component="td" sx={{ p: 1 }}>
              {formatDate(item.last_used_at)}
            </Box>
            <Box component="td" sx={{ p: 1 }}>
              {formatDate(item.latest_expires_at)}
            </Box>
            <Box component="td" sx={{ p: 1 }}>
              <Button
                size="small"
                aria-label={`Revoke ${item.client_name}`}
                onClick={() => onRevoke(item)}
              >
                Revoke
              </Button>
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}
