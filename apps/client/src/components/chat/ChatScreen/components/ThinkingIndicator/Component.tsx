import { Box, CircularProgress, Typography } from '@/components/common';
import { THINKING_LABEL } from '@/lib/copy';

// phase-8 task-12 (DESIGN.md §B4). Zero-prop leaf (docs/FRONTEND-CONVENTIONS.md §3): shown by
// `ChatScreen` between the user's question and the first streamed token. `role="status"` +
// `aria-live="polite"` announces it to assistive tech without interrupting; a real
// `CircularProgress` gives sighted users a spinner, not just text.
export default function Component() {
  return (
    <Box
      role="status"
      aria-live="polite"
      sx={{ display: 'flex', alignItems: 'center', gap: 1, my: 1 }}
    >
      <CircularProgress size={16} />
      <Typography variant="body2" color="text.secondary">
        {THINKING_LABEL}
      </Typography>
    </Box>
  );
}
