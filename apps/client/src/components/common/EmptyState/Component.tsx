import { Box } from '../Box';
import { Button } from '../Button';
import { Icon } from '../Icon';
import { Typography } from '../Typography';
import type { EmptyStateProps } from './interface';

// docs/FRONTEND-CONVENTIONS.md §9: loading/empty/error states are explicit components, never a
// silent blank region. `role="status"` (polite live region) mirrors the existing precedent,
// apps/admin/src/components/common/EmptyState/Component.tsx (task-04 test-author report,
// ambiguity #2 — controller-confirmed).
//
// phase-8 task-06: `icon` (defaults to 'Article', the existing look) and an optional `action`
// (a way out of the empty state, e.g. "Show all") added.
export default function Component({ message, icon, action }: EmptyStateProps) {
  return (
    <Box role="status" sx={{ textAlign: 'center', py: 6 }}>
      <Icon name={icon ?? 'Article'} size="large" />
      <Typography component="p" sx={{ mt: 1 }}>
        {message}
      </Typography>
      {action ? (
        <Box sx={{ mt: 2 }}>
          <Button variant="outlined" href={action.href}>
            {action.label}
          </Button>
        </Box>
      ) : null}
    </Box>
  );
}
