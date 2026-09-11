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

const SKELETON_ROW_COUNT = 3;
const COLUMN_COUNT = 4;

// phase-8 task-21 (DESIGN.md §2, §5 C6): three skeleton rows in the same table shape as the
// loaded state (Client/Connected/Last used/Actions), so the first page load doesn't jump/reflow
// once real rows arrive — mirrors ContentTableSkeleton's idiom (task-18).
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
            <TableCell>Client</TableCell>
            <TableCell>Connected</TableCell>
            <TableCell>Last used</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {Array.from({ length: SKELETON_ROW_COUNT }, (_, rowIndex) => (
            <TableRow key={rowIndex}>
              {Array.from({ length: COLUMN_COUNT }, (_, columnIndex) => (
                <TableCell key={columnIndex}>
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
