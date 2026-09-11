import {
  Chip,
  IconButton,
  Link,
  Paper,
  Stack,
  StatusChip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from '@/components/common';
import { formatDate } from '@/lib/format';
import { CONTENT_TABLE_LABEL, DELETE_LABEL, EDIT_LABEL } from '@/lib/copy';

import type { ContentTableProps } from './interface';

// phase-8 task-18 (DESIGN.md §2, §5 C4): a real MUI table — outlined container that scrolls
// horizontally on phones instead of squeezing columns unreadably narrow.
export default function Component({ items, onDeleteClick }: ContentTableProps) {
  return (
    <TableContainer<typeof Paper> component={Paper} variant="outlined" sx={{ overflowX: 'auto' }}>
      <Table aria-label={CONTENT_TABLE_LABEL}>
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
          {items.map((item) => (
            <TableRow hover key={item.id}>
              <TableCell>
                <Link href={`/content/${item.id}`}>{item.title}</Link>
              </TableCell>
              <TableCell>
                <StatusChip status={item.status} />
              </TableCell>
              <TableCell>
                <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap' }}>
                  {item.tags.map((itemTag) => (
                    <Chip key={itemTag} size="small" variant="outlined" label={itemTag} />
                  ))}
                </Stack>
              </TableCell>
              <TableCell>{formatDate(item.updated_at)}</TableCell>
              <TableCell align="right">
                <IconButton
                  name="Edit"
                  label={`Edit ${item.title}`}
                  href={`/content/${item.id}`}
                  size="small"
                  tooltip={EDIT_LABEL}
                />
                <IconButton
                  name="Delete"
                  label={`Delete ${item.title}`}
                  onClick={() => onDeleteClick(item)}
                  size="small"
                  color="error"
                  tooltip={DELETE_LABEL}
                />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
