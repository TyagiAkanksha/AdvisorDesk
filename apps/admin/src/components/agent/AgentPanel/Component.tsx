'use client';

import type { FormEvent } from 'react';
import { useState } from 'react';

import { Box, Button, ErrorState, TextField, Typography } from '@/components/common';

import { AgentMessage } from '../AgentMessage';
import { useAgentStream } from '../useAgentStream';

// phase-5 task-04, PRD §2.2. The client island: like `apps/client`'s `ChatScreen`, this is the
// panel that owns `useAgentStream()` itself and takes no props (zero-prop component, no
// `interface.ts`, docs/FRONTEND-CONVENTIONS.md §3) — the AppShell controls only its VISUAL
// open/closed state from outside (wraps it in a `Drawer`), never remounts it, so the
// conversation held in `useAgentStream`'s state survives navigation (brief's Interfaces
// section). Input is disabled while streaming (belt-and-suspenders on top of the hook's own
// re-entrancy guard).
const EMPTY_STATE_MESSAGE =
  'Ask the agent to draft, publish, tag, or search content — e.g. "Draft an article on Roth IRA conversion basics and tag it retirement."';

export default function Component() {
  const { turns, streaming, error, send } = useAgentStream();
  const [draft, setDraft] = useState('');

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = draft.trim();
    if (text.length === 0 || streaming) {
      return;
    }
    send(text);
    setDraft('');
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', p: 2 }}>
      <Typography variant="h6" component="h2" sx={{ mb: 1 }}>
        Agent
      </Typography>
      <Box sx={{ flexGrow: 1, overflowY: 'auto' }}>
        {turns.length === 0 ? (
          <Box role="status" sx={{ color: 'text.secondary', py: 2 }}>
            <Typography variant="body2" component="p">
              {EMPTY_STATE_MESSAGE}
            </Typography>
          </Box>
        ) : (
          turns.map((turn, index) => (
            // Index-as-key is safe here: `turns` is append-only, never reordered or spliced
            // (same rationale as `apps/client`'s `ChatScreen`).
            <AgentMessage key={index} turn={turn} />
          ))
        )}
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
