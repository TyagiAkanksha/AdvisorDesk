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

const SKELETON_ROW_COUNT = 5;
const COLUMN_COUNT = 5;

// phase-8 task-18 (DESIGN.md §2, §5 C4): five skeleton rows in the same table shape as the
// loaded state, so the first page load doesn't jump/reflow once real rows arrive.
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
            <TableCell>Title</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Tags</TableCell>
            <TableCell>Updated</TableCell>
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
