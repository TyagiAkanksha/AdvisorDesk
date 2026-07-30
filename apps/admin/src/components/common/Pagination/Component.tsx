import MuiPagination from '@mui/material/Pagination';

import { Box } from '../Box';
import type { PaginationProps } from './interface';

export default function Component({ page, pageSize, total, onPageChange }: PaginationProps) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const rangeStart = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const rangeEnd = Math.min(page * pageSize, total);

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
        {total === 0 ? 'No items' : `Showing ${rangeStart}–${rangeEnd} of ${total}`}
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
