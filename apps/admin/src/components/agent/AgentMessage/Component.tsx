import { Box, Typography } from '@/components/common';

import { ToolCallCard } from '../ToolCallCard';
import type { AgentMessageProps } from './interface';

// phase-5 task-04. Dumb, one purpose: render one turn. `role="article"` named "You"/"Assistant"
// per turn (test-author judgment call, `p5-t04-test-author.md`) — a `Box component="article"`
// carries that role implicitly, same as `apps/client`'s `MessageBubble` precedent for the
// equivalent chat-shaped UI. Tool events render below the turn's text, in arrival order
// (`turn.events` is append-only — index-as-key is safe, same rationale as `ChatScreen`'s own
// message list).
export default function Component({ turn }: AgentMessageProps) {
  const label = turn.role === 'user' ? 'You' : 'Assistant';

  return (
    <Box
      component="article"
      aria-label={label}
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: turn.role === 'user' ? 'flex-end' : 'flex-start',
        mb: 2,
      }}
    >
      <Box
        sx={{
          maxWidth: '90%',
          bgcolor: turn.role === 'user' ? 'primary.main' : 'grey.100',
          color: turn.role === 'user' ? 'primary.contrastText' : 'text.primary',
          borderRadius: 2,
          px: 2,
          py: 1,
        }}
      >
        <Typography component="p" sx={{ color: 'inherit', whiteSpace: 'pre-wrap' }}>
          {turn.text}
        </Typography>
        {turn.events.map((event, index) => (
          <ToolCallCard key={index} event={event} />
        ))}
      </Box>
    </Box>
  );
}
