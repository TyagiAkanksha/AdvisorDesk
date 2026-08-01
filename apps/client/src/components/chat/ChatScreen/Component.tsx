'use client';

import type { FormEvent } from 'react';
import { useState } from 'react';

import { Box, Button, ErrorState, Icon, TextField, Typography } from '@/components/common';

import { MessageBubble } from '../MessageBubble';
import { useChatStream } from '../useChatStream';

// task-05 (phase-4), PRD §2.2. The client island: unlike the RSC `content/` screens, this
// screen owns its own VM hook (docs/FRONTEND-CONVENTIONS.md §6) and takes no props — a zero-prop
// component has no `interface.ts` (§3; brief's Files list disagrees, conventions win — plan-
// conflict ruling, `p4-t05-review.md` §6.1). Input is disabled while streaming to prevent
// overlapping sends (belt-and-suspenders on top of `useChatStream`'s own re-entrancy guard,
// review round 1 M-4); a stream/rate-limit error (PRD §9) surfaces through `ErrorState`'s
// existing friendly-copy contract, never a raw envelope.
//
// task-05 review round 1, M-8: a fresh `/chat` used to be a bare, unexplained input. The block
// below (icon + heading + one-line prompt suggestion, `role="status"`) mirrors
// `common/EmptyState`'s existing icon-centered idiom (docs/FRONTEND-CONVENTIONS.md §9) without
// reusing that component verbatim — `EmptyState` takes a single `message` string, and this needs
// a heading plus a distinct example line. It unmounts the instant the first message lands
// (`messages.length === 0`), so it never coexists with a `role="status"` refusal.
const EXAMPLE_QUESTION = 'When can I withdraw from a Roth IRA without penalty?';

export default function Component() {
  const { messages, streaming, error, send } = useChatStream();
  const [draft, setDraft] = useState('');

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const question = draft.trim();
    if (question.length === 0 || streaming) {
      return;
    }
    send(question);
    setDraft('');
  };

  return (
    <Box>
      <Box sx={{ display: 'flex', flexDirection: 'column' }}>
        {messages.length === 0 && (
          <Box role="status" sx={{ textAlign: 'center', color: 'text.secondary', py: 6 }}>
            <Icon name="Chat" size="large" />
            <Typography variant="h6" component="p" sx={{ mt: 1 }}>
              Ask about our published guidance
            </Typography>
            <Typography variant="body2" component="p" sx={{ mt: 0.5 }}>
              Try: &ldquo;{EXAMPLE_QUESTION}&rdquo;
            </Typography>
          </Box>
        )}
        {messages.map((message, index) => (
          // Index-as-key is safe here: `messages` is append-only, never reordered or spliced.
          <MessageBubble key={index} message={message} />
        ))}
      </Box>
      {error !== null && <ErrorState message={error} />}
      <form onSubmit={handleSubmit}>
        <Box sx={{ display: 'flex', gap: 1, mt: 2 }}>
          <TextField
            label="Message"
            value={draft}
            onChange={setDraft}
            disabled={streaming}
            fullWidth
          />
          <Button type="submit" disabled={streaming}>
            Send
          </Button>
        </Box>
      </form>
    </Box>
  );
}
