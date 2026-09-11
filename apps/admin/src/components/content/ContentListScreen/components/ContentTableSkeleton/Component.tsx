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

import { CONTENT_TABLE_COLUMNS } from '../ContentTable/columns';

const SKELETON_ROW_COUNT = 5;

// phase-8 task-18 (DESIGN.md §2, §5 C4): five skeleton rows in the same table shape as the
// loaded state, so the first page load doesn't jump/reflow once real rows arrive. p8 final, F13:
// both the header and each row map over the shared `CONTENT_TABLE_COLUMNS` — the skeleton's cell
// count can never drift from `ContentTable`'s own header.
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
            {CONTENT_TABLE_COLUMNS.map((column) => (
              <TableCell key={column.label} align={column.align}>
                {column.label}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {Array.from({ length: SKELETON_ROW_COUNT }, (_, rowIndex) => (
            <TableRow key={rowIndex}>
              {CONTENT_TABLE_COLUMNS.map((column) => (
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
