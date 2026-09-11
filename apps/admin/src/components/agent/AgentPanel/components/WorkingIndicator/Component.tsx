import { CircularProgress, Stack, Typography } from '@/components/common';
import { AGENT_WORKING_LABEL } from '@/lib/copy';

// phase-8 task-23 (DESIGN.md §5 C7). Zero-prop leaf: shown while `useAgentStream().streaming`.
export default function Component() {
  return (
    <Stack
      direction="row"
      spacing={1}
      role="status"
      aria-label={AGENT_WORKING_LABEL}
      sx={{ alignItems: 'center', py: 1 }}
    >
      <CircularProgress size={16} aria-hidden />
      <Typography variant="body2" color="text.secondary">
        {AGENT_WORKING_LABEL}
      </Typography>
    </Stack>
  );
}
