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
        // p8 final, F10(a): the chevron rotates 180° when expanded — a small affordance that the
        // row toggles rather than navigates. Purely visual (`aria-hidden` on the glyph itself);
        // `aria-expanded` above already carries the state for assistive tech.
        startIcon={
          <Box
            component="span"
            sx={{
              display: 'inline-flex',
              transform: expanded ? 'rotate(180deg)' : 'none',
              transition: 'transform 150ms',
            }}
          >
            <Icon name="ExpandMore" />
          </Box>
        }
        sx={{
          justifyContent: 'flex-start',
          textAlign: 'left',
          fontFamily: 'monospace',
          fontSize: '0.8125rem',
        }}
      >
        {/* p8 final, F19: single-line, ellipsized when the summary (esp. an untruncated result)
            overflows — the full text still lives in the expanded Result block below. Visual only:
            the accessible-name computation reads this span's text content regardless of the CSS
            truncation, so the button's pinned accessible name is unaffected. */}
        <Box
          component="span"
          sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}
        >
          {summary}
        </Box>
      </Button>
      {expanded ? (
        <Box sx={{ px: 2, pb: 2 }}>
          {/* p8 final, F10(b): an orphan tool_result (no matching tool_call) carries no
              arguments — `segment.args` is `''` — so there is nothing to caption or pretty-print. */}
          {segment.args !== '' ? (
            <>
              <Typography variant="caption" color="text.secondary" component="p">
                {TOOL_ARGUMENTS_LABEL}
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
                {prettyJson(segment.args)}
              </Box>
            </>
          ) : null}
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
