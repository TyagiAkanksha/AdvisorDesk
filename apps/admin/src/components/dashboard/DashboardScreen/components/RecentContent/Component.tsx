import {
  EmptyState,
  Link,
  StatusChip,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
} from '@/components/common';
import { NO_RECENT_CONTENT_MESSAGE, RECENT_CONTENT_TITLE } from '@/lib/copy';
import { formatDate } from '@/lib/format';

import type { RecentContentProps } from './interface';

// task-17 (DESIGN.md §2, §5 C3): the dashboard's "Recent content" panel — five rows from
// `GET /api/v1/content` (title link, status chip, formatted updated date).
export default function Component({ items }: RecentContentProps) {
  if (items.length === 0) {
    return <EmptyState message={NO_RECENT_CONTENT_MESSAGE} />;
  }

  return (
    <Table size="small" aria-label={RECENT_CONTENT_TITLE}>
      <TableHead>
        <TableRow>
          <TableCell>Title</TableCell>
          <TableCell>Status</TableCell>
          <TableCell>Updated</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {items.map((item) => (
          <TableRow key={item.id}>
            <TableCell>
              <Link href={`/content/${item.id}`}>{item.title}</Link>
            </TableCell>
            <TableCell>
              <StatusChip status={item.status} />
            </TableCell>
            <TableCell>{formatDate(item.updated_at)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
