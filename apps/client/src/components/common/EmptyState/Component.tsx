import { Box } from '../Box';
import { Button } from '../Button';
import { Icon } from '../Icon';
import { Typography } from '../Typography';
import type { EmptyStateProps } from './interface';

// docs/FRONTEND-CONVENTIONS.md §9: loading/empty/error states are explicit components, never a
// silent blank region. `role="status"` (polite live region) wraps only the icon + text; the
// optional `action` is a sibling after it — controls must not live inside a live region
// (hygiene t03, t23 M5).
//
// phase-8 task-06: `icon` (defaults to 'Article', the existing look) and an optional `action`
// (a way out of the empty state, e.g. "Show all") added.
export default function Component({ message, icon, action }: EmptyStateProps) {
  return (
    <Box sx={{ textAlign: 'center', py: 6 }}>
      <Box role="status">
        <Icon name={icon ?? 'Article'} size="large" />
        <Typography component="p" sx={{ mt: 1 }}>
          {message}
        </Typography>
      </Box>
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
