import {
  EmptyState,
  Link,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
} from '@/components/common';
import { CONTENT_BY_TAG_TITLE, NO_TAGS_MESSAGE } from '@/lib/copy';

import type { TagTableProps } from './interface';

// task-17 (DESIGN.md §2, §5 C3): the dashboard's "Content by tag" panel — each tag name links
// to the tag-filtered content list.
export default function Component({ rows }: TagTableProps) {
  if (rows.length === 0) {
    return <EmptyState message={NO_TAGS_MESSAGE} />;
  }

  return (
    <Table size="small" aria-label={CONTENT_BY_TAG_TITLE}>
      <TableHead>
        <TableRow>
          <TableCell>Tag</TableCell>
          <TableCell>Count</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.tag}>
            <TableCell>
              <Link href={`/content?tag=${encodeURIComponent(row.tag)}`}>{row.tag}</Link>
            </TableCell>
            <TableCell>{row.count}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
