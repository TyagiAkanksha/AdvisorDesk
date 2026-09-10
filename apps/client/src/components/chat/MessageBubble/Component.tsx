import { Box, Icon, Typography } from '@/components/common';
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
// task-05 review round 1 (I-1, I-2): both findings were "semantically distinct, visually
// identical" — a sighted user could only infer a refusal from the ABSENCE of citation chips, and
// user/assistant turns rendered as an undifferentiated transcript (the "You"/"Assistant" labels
// existed only in `aria-label`). Fixed with theme-token-driven styling only (no hardcoded hex):
// user turns are right-aligned, `primary.main`-filled bubbles; assistant turns are left-aligned,
// neutral (`grey.100`) bubbles; a refusal additionally gets a bordered `warning`-toned panel and
// an `Info` icon, distinct from both. `role="status"`/`role="article"` and every pinned
// accessible name are unchanged — this is a pure presentation layer on top of them.
const BUBBLE_MAX_WIDTH = '75%';

export default function Component({ message }: MessageBubbleProps) {
  if (message.role === 'user') {
    return (
      <Box
        component="article"
        aria-label="You"
        sx={{ display: 'flex', justifyContent: 'flex-end', mb: 2 }}
      >
        <Box
          sx={{
            maxWidth: BUBBLE_MAX_WIDTH,
            bgcolor: 'primary.main',
            color: 'primary.contrastText',
            borderRadius: 2,
            px: 2,
            py: 1,
          }}
        >
          <Typography component="p" sx={{ color: 'inherit' }}>
            {message.text}
          </Typography>
        </Box>
      </Box>
    );
  }

  const citations = message.citations ?? [];
  const answer = (
    <>
      <Markdown markdown={message.text} variant="chat" />
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
        <Box
          role="status"
          sx={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 1,
            maxWidth: BUBBLE_MAX_WIDTH,
            bgcolor: 'warning.light',
            border: 1,
            borderColor: 'warning.main',
            borderRadius: 2,
            px: 2,
            py: 1.5,
          }}
        >
          <Icon name="Info" label="No published guidance" size="small" />
          <Box sx={{ minWidth: 0 }}>{answer}</Box>
        </Box>
      ) : (
        <Box
          sx={{ maxWidth: BUBBLE_MAX_WIDTH, bgcolor: 'grey.100', borderRadius: 2, px: 2, py: 1 }}
        >
          {answer}
        </Box>
      )}
    </Box>
  );
}
