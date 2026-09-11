import {
  Paper,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from '@/components/common';
import { LOADING_LABEL } from '@/lib/copy';

import { CONNECTED_APPS_TABLE_COLUMNS } from '../ConnectedAppsTable/columns';

const SKELETON_ROW_COUNT = 3;

// phase-8 task-21 (DESIGN.md §2, §5 C6): three skeleton rows in the same table shape as the
// loaded state (Client/Connected/Last used/Actions), so the first page load doesn't jump/reflow
// once real rows arrive — mirrors ContentTableSkeleton's idiom (task-18). p8 final, F13: both the
// header and each row map over the shared `CONNECTED_APPS_TABLE_COLUMNS`.
export default function Component() {
  return (
    <TableContainer<typeof Paper>
      component={Paper}
      variant="outlined"
      sx={{ overflowX: 'auto' }}
      role="status"
      aria-label={LOADING_LABEL}
    >
      <Table>
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
          {Array.from({ length: SKELETON_ROW_COUNT }, (_, rowIndex) => (
            <TableRow key={rowIndex}>
              {CONNECTED_APPS_TABLE_COLUMNS.map((column) => (
                <TableCell key={column.label}>
                  <Skeleton variant="text" />
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
