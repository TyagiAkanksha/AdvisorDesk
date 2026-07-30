import { Box } from '../Box';
import { Icon } from '../Icon';
import type { EmptyStateProps } from './interface';

// docs/FRONTEND-CONVENTIONS.md §9: loading/empty/error states are explicit components, never a
// silent blank region. `role="status"` (polite live region) — reused by task-06 and phase-5.
export default function Component({ message }: EmptyStateProps) {
  return (
    <Box role="status" sx={{ textAlign: 'center', color: 'text.secondary', py: 6 }}>
      <Icon name="Article" size="large" />
      <Box component="p" sx={{ mt: 1 }}>
        {message}
      </Box>
    </Box>
  );
}
