import MuiPagination from '@mui/material/Pagination';

import { Box } from '../Box';
import type { PaginationProps } from './interface';

// Final review, finding F7 (t05 M10+M11): `total === 0` suppresses the pager entirely (return
// `null`) — there is nothing to page through and no escape hatch needed. A STRANDED page
// (`total > 0` but `rangeStart > total`, e.g. deleting the sole row on the last page) is a
// different case: the same "No items" affordance as the zero-total case, but the `MuiPagination`
// control itself stays mounted, since it is the only way back to an earlier page
// (ContentListScreen/pagination.test.tsx's stranded-page test).
export default function Component({ page, pageSize, total, onPageChange }: PaginationProps) {
  if (total === 0) {
    return null;
  }

  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const rangeStart = (page - 1) * pageSize + 1;
  const rangeEnd = Math.min(page * pageSize, total);
  const isStranded = rangeStart > total;

  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 1,
        mt: 2,
      }}
    >
      <Box component="span" sx={{ color: 'text.secondary', fontSize: '0.875rem' }}>
        {isStranded ? 'No items' : `Showing ${rangeStart}–${rangeEnd} of ${total}`}
      </Box>
      <MuiPagination
        page={page}
        count={pageCount}
        onChange={(_event, value) => onPageChange(value)}
        color="primary"
        size="small"
      />
    </Box>
  );
}
