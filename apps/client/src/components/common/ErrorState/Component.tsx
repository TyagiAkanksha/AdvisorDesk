import { Typography } from '../Typography';
import type { ErrorStateProps } from './interface';

const DEFAULT_MESSAGE = 'Something went wrong. Please try again.';

// task-04 fix round 1 (F4), docs/FRONTEND-CONVENTIONS.md §9: loading/empty/error states are
// explicit components, never a silent blank region; raw API error bodies are never rendered
// here — only friendly, authored copy. `role="alert"` (assertive live region) mirrors
// apps/admin/src/components/common/ErrorState/Component.tsx — apps/client/common has no `Box`
// primitive (task-04 deliberately didn't add one; see that task's implementer report), so this
// uses a plain `<div>` wrapper instead of admin's `Box`.
export default function Component({ message = DEFAULT_MESSAGE }: ErrorStateProps) {
  return (
    <div role="alert">
      <Typography component="p" color="error.main" sx={{ textAlign: 'center', py: 6 }}>
        {message}
      </Typography>
    </div>
  );
}
