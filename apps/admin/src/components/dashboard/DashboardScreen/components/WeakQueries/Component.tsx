import {
  Chip,
  EmptyState,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
} from '@/components/common';
import { NO_WEAK_QUERIES_MESSAGE, WEAK_QUERIES_ARIA_LABEL } from '@/lib/copy';
import { WEAK_QUERY_KIND_COLORS, WEAK_QUERY_KIND_LABELS } from '@/types/api/weakQueries';

import type { WeakQueriesProps } from './interface';

// phase-9 task-19 (DESIGN §D): the dashboard's "Weak queries" panel — one row per normalised
// question, aggregated across every weak turn that asked it (`GET /api/v1/weak-queries`).
export default function Component({ items }: WeakQueriesProps) {
  if (items.length === 0) {
    return <EmptyState message={NO_WEAK_QUERIES_MESSAGE} />;
  }

  return (
    <Table size="small" aria-label={WEAK_QUERIES_ARIA_LABEL}>
      <TableHead>
        <TableRow>
          <TableCell>Question</TableCell>
          <TableCell>Kinds</TableCell>
          <TableCell>Asked</TableCell>
          <TableCell>Worst similarity</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {items.map((item) => (
          <TableRow key={item.normalized_question}>
            <TableCell>{item.normalized_question}</TableCell>
            <TableCell>
              <Stack direction="row" spacing={0.5}>
                {item.kinds.map((kind) => (
                  <Chip
                    key={kind}
                    size="small"
                    label={WEAK_QUERY_KIND_LABELS[kind] ?? kind}
                    color={WEAK_QUERY_KIND_COLORS[kind] ?? 'default'}
                  />
                ))}
              </Stack>
            </TableCell>
            <TableCell>×{item.count}</TableCell>
            <TableCell>
              {item.worst_top_similarity === null ? '—' : item.worst_top_similarity.toFixed(2)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
