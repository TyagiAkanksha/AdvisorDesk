import { useState } from 'react';

import { Box, Button, Icon, Paper, Typography } from '@/components/common';
import {
  TOOL_ARGUMENTS_LABEL,
  TOOL_RAN_PREFIX,
  TOOL_RESULT_LABEL,
  TOOL_RUNNING_PREFIX,
} from '@/lib/copy';

import type { ToolCallCardProps } from './interface';

// phase-8 task-23 (DESIGN.md §5 C7): a collapsible card for one tool segment
// (`lib/agentTurnSegments.ts`'s `ToolSegment`) — collapsed to "Running <tool>…" while there's no
// result yet, or "Ran <tool> · <summary>" once there is; expanding shows the pretty-printed
// arguments and (once it arrives) the result, each in a `<pre>` block. `expanded` is local UI
// state — this card has no memory of its own beyond the current render.
function prettyJson(raw: string): string {
  if (raw === '') {
    return raw;
  }
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

export default function Component({ segment }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false);

  const summary =
    segment.result === null
      ? `${TOOL_RUNNING_PREFIX} ${segment.tool}…`
      : `${TOOL_RAN_PREFIX} ${segment.tool} · ${segment.result}`;

  return (
    <Paper variant="outlined" sx={{ my: 1 }}>
      <Button
        variant="text"
        fullWidth
        onClick={() => setExpanded((prev) => !prev)}
        aria-expanded={expanded}
        startIcon={<Icon name="ExpandMore" />}
        sx={{
          justifyContent: 'flex-start',
          textAlign: 'left',
          fontFamily: 'monospace',
          fontSize: '0.8125rem',
        }}
      >
        {summary}
      </Button>
      {expanded ? (
        <Box sx={{ px: 2, pb: 2 }}>
          <Typography variant="caption" color="text.secondary" component="p">
            {TOOL_ARGUMENTS_LABEL}
          </Typography>
          <Box
            component="pre"
            sx={{ m: 0, fontSize: '0.8125rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
          >
            {prettyJson(segment.args)}
          </Box>
          {segment.result !== null ? (
            <>
              <Typography variant="caption" color="text.secondary" component="p" sx={{ mt: 1 }}>
                {TOOL_RESULT_LABEL}
              </Typography>
              <Box
                component="pre"
                sx={{
                  m: 0,
                  fontSize: '0.8125rem',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {segment.result}
              </Box>
            </>
          ) : null}
        </Box>
      ) : null}
    </Paper>
  );
}
