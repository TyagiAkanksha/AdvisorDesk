import { Box, Typography } from '@/components/common';

import type { ToolCallCardProps } from './interface';

// phase-5 task-04, brief's ToolCallCard contract (verbatim wire-up): a `'call'` event renders
// "→ create_draft {title:…}"; a `'result'` event renders "✓ create_draft — <result_summary>".
// Dumb — renders one already-parsed `ToolEvent`, no logic of its own.
export default function Component({ event }: ToolCallCardProps) {
  const text =
    event.kind === 'call' ? `→ ${event.tool} ${event.detail}` : `✓ ${event.tool} — ${event.detail}`;

  return (
    <Box sx={{ mt: 0.5 }}>
      <Typography
        component="p"
        variant="body2"
        sx={{ fontFamily: 'monospace', color: 'text.secondary' }}
      >
        {text}
      </Typography>
    </Box>
  );
}
