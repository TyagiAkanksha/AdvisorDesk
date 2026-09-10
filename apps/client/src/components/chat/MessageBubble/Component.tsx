import { Alert, Box, Paper, Typography } from '@/components/common';
import { Markdown } from '@/components/content/Markdown';

import { CitationList } from '../CitationList';
import type { MessageBubbleProps } from './interface';

// task-05 (phase-4), PRD §2.2/§5.3. Dumb, one purpose: render one turn. `role="article"` named
// "You"/"Assistant" per message (test-author judgment call, `p4-t05-test-author.md`) — a `Box
// component="article"` carries that role implicitly, same as a native `<article>`, while gaining
// `sx` (docs/FRONTEND-CONVENTIONS.md §4's `common/Box`). A refusal (`refusal: true`, PRD
// §7.4/§7.5) wraps its content in `role="status"`, mirroring `common/EmptyState`'s existing
// precedent (docs/FRONTEND-CONVENTIONS.md §9) rather than inventing a new pattern.
//
// phase-8 task-12 (DESIGN.md §B4): navy/outlined `Paper` bubbles (replacing the old hand-styled
// `grey.100`/`primary.main` `Box`es) capped at 640px so a wide viewport doesn't stretch a chat
// turn edge-to-edge; a refusal is now a real `common/Alert` (`severity="warning"
// variant="outlined"`) instead of a bordered `Box` + `Info` icon — same pinned `role="status"` +
// text, MUI's own warning styling.
const BUBBLE_MAX_WIDTH = 'min(100%, 640px)';

export default function Component({ message }: MessageBubbleProps) {
  if (message.role === 'user') {
    return (
      <Box
        component="article"
        aria-label="You"
        sx={{ display: 'flex', justifyContent: 'flex-end', mb: 2 }}
      >
        <Paper
          elevation={0}
          sx={{
            bgcolor: 'primary.main',
            color: 'primary.contrastText',
            px: 2,
            py: 1.5,
            borderRadius: 2,
            maxWidth: BUBBLE_MAX_WIDTH,
          }}
        >
          <Typography component="p" sx={{ color: 'inherit' }}>
            {message.text}
          </Typography>
        </Paper>
      </Box>
    );
  }

  const citations = message.citations ?? [];
  const answer = (
    <>
      <Markdown markdown={message.text} variant="chat" headingOffset={1} />
      <CitationList citations={citations} />
    </>
  );

  return (
    <Box
      component="article"
      aria-label="Assistant"
      sx={{ display: 'flex', justifyContent: 'flex-start', mb: 2 }}
    >
      {message.refusal ? (
        <Alert
          severity="warning"
          variant="outlined"
          role="status"
          sx={{ maxWidth: BUBBLE_MAX_WIDTH }}
        >
          {answer}
        </Alert>
      ) : (
        <Paper
          variant="outlined"
          sx={{ px: 2, py: 1.5, borderRadius: 2, maxWidth: BUBBLE_MAX_WIDTH }}
        >
          {answer}
        </Paper>
      )}
    </Box>
  );
}
