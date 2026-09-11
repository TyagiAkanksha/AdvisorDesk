import { Box, IconButton, Stack, TextField, Typography } from '@/components/common';
import {
  AGENT_HELPER_TEXT,
  AGENT_MESSAGE_LABEL,
  AGENT_SEND_LABEL,
  AGENT_STOP_LABEL,
} from '@/lib/copy';

import type { AgentComposerProps } from './interface';

// phase-8 task-23 (DESIGN.md §5 C7). Dumb leaf: a multiline composer with a helper line and a
// Send/Stop swap — all state and keyboard rules live in `useAgentComposer`/`useAgentStream`.
export default function Component({
  value,
  onChange,
  onKeyDown,
  onSubmit,
  canSend,
  streaming,
  onStop,
}: AgentComposerProps) {
  return (
    <Box
      component="form"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
      sx={{ p: 2, borderTop: 1, borderColor: 'divider' }}
    >
      <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-end' }}>
        <TextField
          label={AGENT_MESSAGE_LABEL}
          value={value}
          onChange={onChange}
          multiline
          maxRows={4}
          fullWidth
          disabled={streaming}
          onKeyDown={onKeyDown}
        />
        {streaming ? (
          <IconButton name="Stop" label={AGENT_STOP_LABEL} onClick={onStop} color="primary" />
        ) : (
          <IconButton
            name="Send"
            label={AGENT_SEND_LABEL}
            onClick={onSubmit}
            color="primary"
            disabled={!canSend}
          />
        )}
      </Stack>
      <Typography variant="caption" color="text.secondary" component="p" sx={{ mt: 0.5 }}>
        {AGENT_HELPER_TEXT}
      </Typography>
    </Box>
  );
}
