import { Icon } from '../Icon';
import { Typography } from '../Typography';
import type { EmptyStateProps } from './interface';

// docs/FRONTEND-CONVENTIONS.md §9: loading/empty/error states are explicit components, never a
// silent blank region. `role="status"` (polite live region) mirrors the existing precedent,
// apps/admin/src/components/common/EmptyState/Component.tsx (task-04 test-author report,
// ambiguity #2 — controller-confirmed).
export default function Component({ message }: EmptyStateProps) {
  return (
    <div role="status">
      <Icon name="Article" size="large" />
      <Typography component="p" sx={{ mt: 1 }}>
        {message}
      </Typography>
    </div>
  );
}
