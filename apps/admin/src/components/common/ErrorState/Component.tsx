import { Box } from '../Box';
import { Button } from '../Button';
import type { ErrorStateProps } from './interface';

const DEFAULT_MESSAGE = 'Something went wrong. Please try again.';

// docs/FRONTEND-CONVENTIONS.md §9: loading/empty/error states are explicit components, never a
// silent blank region; raw API error bodies are never rendered here — only friendly, authored
// copy. `role="alert"` (assertive live region) — reused by task-06 and phase-5.
export default function Component({ message = DEFAULT_MESSAGE, action }: ErrorStateProps) {
  return (
    <Box role="alert" sx={{ textAlign: 'center', color: 'error.main', py: 6 }}>
      {message}
      {action ? (
        // `Button` (docs/FRONTEND-CONVENTIONS.md §4: a bespoke contract, not a raw MUI
        // pass-through) does not expose `sx` — the mt:2 spacing lives on this wrapping Box.
        <Box sx={{ mt: 2 }}>
          <Button variant="outlined" onClick={action.onClick}>
            {action.label}
          </Button>
        </Box>
      ) : null}
    </Box>
  );
}
