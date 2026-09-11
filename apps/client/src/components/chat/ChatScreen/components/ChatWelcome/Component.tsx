import { Box, Button, Stack, Typography } from '@/components/common';
import { CHAT_DESCRIPTION, CHAT_TITLE, SUGGESTED_QUESTIONS } from '@/lib/copy';

import type { ChatWelcomeProps } from './interface';

// phase-8 task-12 (DESIGN.md §B4). The empty-transcript state: a one-line explanation of where
// answers come from and four clickable suggested questions — a fresh `/chat` is no longer a
// bare, unexplained input. `role="region"` (not `role="status"`): this is page content the user
// reads and acts on, not a live announcement.
//
// p8 t24 (DESIGN.md §B4 carry-in): the page h1 now lives in `ChatScreen` (it persists across a
// conversation) — this region renders no heading of its own.
export default function Component({ onAsk }: ChatWelcomeProps) {
  return (
    <Box role="region" aria-label={CHAT_TITLE}>
      <Typography variant="body1" color="text.secondary">
        {CHAT_DESCRIPTION}
      </Typography>
      {/* MUI 9's Stack no longer exposes flexWrap/alignItems/justifyContent as direct props
          (only children/direction/spacing/divider/useFlexGap/sx) — the wrap goes through `sx`. */}
      <Stack direction="row" useFlexGap spacing={1} sx={{ flexWrap: 'wrap', mt: 2 }}>
        {SUGGESTED_QUESTIONS.map((question) => (
          <Button key={question} variant="outlined" onClick={() => onAsk(question)}>
            {question}
          </Button>
        ))}
      </Stack>
    </Box>
  );
}
