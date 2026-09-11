import { Paper } from '@/components/common';
import { MarkdownPreview } from '@/components/content/MarkdownPreview';
import { turnSegments } from '@/lib/agentTurnSegments';

import { ToolCallCard } from '../ToolCallCard';
import type { AgentMessageProps } from './interface';

// phase-8 task-23 (DESIGN.md §5 C7). Dumb, one purpose: render one turn. `role="article"` named
// "You"/"Assistant" per turn (test-author judgment call carried over from phase-5 task-04). A
// user turn is a right-aligned navy `Paper` bubble; an assistant turn is `turnSegments(turn)`
// mapped onto Markdown text runs and `ToolCallCard`s, INTERLEAVED in arrival order (`turn.events`
// is append-only — index-as-key is safe, same rationale as `ChatScreen`'s own message list).
export default function Component({ turn }: AgentMessageProps) {
  if (turn.role === 'user') {
    return (
      <Paper
        component="article"
        aria-label="You"
        elevation={0}
        sx={{
          ml: 'auto',
          maxWidth: '90%',
          width: 'fit-content',
          bgcolor: 'primary.main',
          color: 'primary.contrastText',
          px: 2,
          py: 1,
          mb: 2,
          whiteSpace: 'pre-wrap',
        }}
      >
        {turn.text}
      </Paper>
    );
  }

  return (
    // p8 final, F18: outlined (not the unmandated `grey.100` fill) — token-consistent with the
    // rest of the admin's Paper surfaces and matches the client chat's own assistant bubble.
    <Paper
      component="article"
      aria-label="Assistant"
      variant="outlined"
      sx={{ maxWidth: '90%', px: 2, py: 1, mb: 2 }}
    >
      {turnSegments(turn).map((segment, index) =>
        segment.kind === 'text' ? (
          <MarkdownPreview key={index} markdown={segment.text} variant="chat" />
        ) : (
          <ToolCallCard key={index} segment={segment} />
        ),
      )}
    </Paper>
  );
}
