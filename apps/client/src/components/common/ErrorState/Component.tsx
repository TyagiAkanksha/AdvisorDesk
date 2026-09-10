import { GENERIC_ERROR_MESSAGE } from '@/lib/copy';

import { Box } from '../Box';
import { Button } from '../Button';
import { Typography } from '../Typography';
import type { ErrorStateProps } from './interface';

// task-04 fix round 1 (F4), docs/FRONTEND-CONVENTIONS.md §9: loading/empty/error states are
// explicit components, never a silent blank region; raw API error bodies are never rendered
// here — only friendly, authored copy. `role="alert"` (assertive live region) mirrors
// apps/admin/src/components/common/ErrorState/Component.tsx.
//
// task-05 review round 1, M-6: the default message comes from `@/lib/copy`'s single shared
// constant instead of a locally-duplicated string.
//
// phase-8 task-06: now uses `Box` (the client app didn't have one at task-04) and renders an
// optional `action` button under the message — the same retry affordance as admin's ErrorState.
export default function Component({ message = GENERIC_ERROR_MESSAGE, action }: ErrorStateProps) {
  return (
    <Box role="alert" sx={{ textAlign: 'center', py: 6 }}>
      <Typography component="p" color="error.main">
        {message}
      </Typography>
      {action ? (
        <Box sx={{ mt: 2 }}>
          <Button variant="outlined" onClick={action.onClick}>
            {action.label}
          </Button>
        </Box>
      ) : null}
    </Box>
  );
}
