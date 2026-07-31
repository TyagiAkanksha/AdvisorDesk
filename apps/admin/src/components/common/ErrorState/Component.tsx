import { Box } from '../Box';
import type { ErrorStateProps } from './interface';

const DEFAULT_MESSAGE = 'Something went wrong. Please try again.';

// docs/FRONTEND-CONVENTIONS.md §9: loading/empty/error states are explicit components, never a
// silent blank region; raw API error bodies are never rendered here — only friendly, authored
// copy. `role="alert"` (assertive live region) — reused by task-06 and phase-5.
export default function Component({ message = DEFAULT_MESSAGE }: ErrorStateProps) {
  return (
    <Box role="alert" sx={{ textAlign: 'center', color: 'error.main', py: 6 }}>
      {message}
    </Box>
  );
}
