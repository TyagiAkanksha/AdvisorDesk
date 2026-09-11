'use client';

import { useEffect, useRef } from 'react';

import { Alert, Box, Button, EmptyState, IconButton, Stack, Typography } from '@/components/common';
import {
  AGENT_CLEAR_LABEL,
  AGENT_CLOSE_LABEL,
  AGENT_EMPTY_DESCRIPTION,
  AGENT_EMPTY_TITLE,
  AGENT_PANEL_TITLE,
  AGENT_SUGGESTED_COMMANDS,
} from '@/lib/copy';

import { AgentMessage } from '../AgentMessage';
import { useAgentStream } from '../useAgentStream';
import { AgentComposer } from './components/AgentComposer';
import { WorkingIndicator } from './components/WorkingIndicator';
import type { AgentPanelProps } from './interface';
import { useAgentComposer } from './useAgentComposer';

// phase-8 task-23 (DESIGN.md §5 C7). The client island: like `apps/client`'s `ChatScreen`, this
// owns `useAgentStream()` itself — the AppShell controls only its VISUAL open/closed state from
// outside (wraps it in a `Drawer`), never remounts it, so the conversation survives navigation.
// `onClose` (the shell's `closeAgent`) is this panel's only prop — its own close button.
export default function Component({ onClose }: AgentPanelProps) {
  const { turns, streaming, error, send, stop, reset } = useAgentStream();
  const composer = useAgentComposer({ disabled: streaming, onSend: send });
  const listRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to the newest turn — a plain `scrollTop` assignment, not `scrollIntoView`
  // (jsdom doesn't implement the latter).
  useEffect(() => {
    const el = listRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [turns]);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Stack
        direction="row"
        spacing={1}
        sx={{ alignItems: 'center', px: 2, py: 1.5, borderBottom: 1, borderColor: 'divider' }}
      >
        <Typography variant="h6" component="h2" sx={{ flexGrow: 1 }}>
          {AGENT_PANEL_TITLE}
        </Typography>
        <Button
          variant="text"
          size="small"
          onClick={reset}
          disabled={turns.length === 0 && !streaming}
        >
          {AGENT_CLEAR_LABEL}
        </Button>
        <IconButton name="Close" label={AGENT_CLOSE_LABEL} onClick={onClose} size="small" />
      </Stack>
      <Box ref={listRef} sx={{ flexGrow: 1, overflowY: 'auto', px: 2, py: 2 }}>
        {turns.length === 0 ? (
          <EmptyState
            icon="SmartToy"
            title={AGENT_EMPTY_TITLE}
            description={AGENT_EMPTY_DESCRIPTION}
            action={
              <Stack spacing={1}>
                {AGENT_SUGGESTED_COMMANDS.map((command) => (
                  <Button
                    key={command}
                    variant="outlined"
                    size="small"
                    onClick={() => send(command)}
                  >
                    {command}
                  </Button>
                ))}
              </Stack>
            }
          />
        ) : (
          turns.map((turn, index) => <AgentMessage key={index} turn={turn} />)
        )}
        {streaming ? <WorkingIndicator /> : null}
      </Box>
      {error !== null ? (
        <Alert severity="error" sx={{ mx: 2, mb: 1 }}>
          {error}
        </Alert>
      ) : null}
      <AgentComposer
        value={composer.draft}
        onChange={composer.setDraft}
        onKeyDown={composer.onKeyDown}
        onSubmit={composer.submit}
        canSend={composer.canSend}
        streaming={streaming}
        onStop={stop}
      />
    </Box>
  );
}
