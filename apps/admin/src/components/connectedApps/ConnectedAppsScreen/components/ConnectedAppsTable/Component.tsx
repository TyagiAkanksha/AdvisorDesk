import {
  Button,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@/components/common';
import { formatOptionalDateTime } from '@/lib/format';
import { CONNECTED_APPS_TABLE_LABEL, REVOKE_LABEL } from '@/lib/copy';

import { CONNECTED_APPS_TABLE_COLUMNS } from './columns';
import type { ConnectedAppsTableProps } from './interface';

// phase-8 task-21 (DESIGN.md §2, §5 C6): a real MUI table — outlined container that scrolls
// horizontally on phones instead of squeezing columns unreadably narrow. Reduced to what an
// admin acts on (Client/Connected/Last used/Revoke) — token counts and expiry are dropped.
// Mirrors ContentTable's `TableContainer<typeof Paper>` pattern (task-18). p8 final, F13: the
// header row maps over `CONNECTED_APPS_TABLE_COLUMNS`, shared with `ConnectedAppsSkeleton`.
export default function Component({ items, onRevoke }: ConnectedAppsTableProps) {
  return (
    <TableContainer<typeof Paper> component={Paper} variant="outlined" sx={{ overflowX: 'auto' }}>
      <Table aria-label={CONNECTED_APPS_TABLE_LABEL}>
        <TableHead>
          <TableRow>
            {CONNECTED_APPS_TABLE_COLUMNS.map((column) => (
              <TableCell key={column.label} align={column.align}>
                {column.label}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {items.map((item) => (
            <TableRow hover key={item.client_id} data-testid={`connected-app-${item.client_id}`}>
              <TableCell>
                <Typography variant="body2" component="div">
                  {item.client_name}
                </Typography>
                <Typography variant="caption" color="text.secondary" component="div">
                  {item.client_id.slice(0, 12)}
                </Typography>
              </TableCell>
              <TableCell>{formatOptionalDateTime(item.consent_granted_at)}</TableCell>
              <TableCell>{formatOptionalDateTime(item.last_used_at)}</TableCell>
              <TableCell align="right">
                <Button
                  variant="outlined"
                  color="error"
                  size="small"
                  aria-label={`Revoke ${item.client_name}`}
                  onClick={() => onRevoke(item)}
                >
                  {REVOKE_LABEL}
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
