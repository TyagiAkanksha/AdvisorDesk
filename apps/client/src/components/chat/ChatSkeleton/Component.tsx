import { Box, Skeleton, Stack } from '@/components/common';
import { LOADING_LABEL } from '@/lib/copy';

const SUGGESTED_QUESTION_COUNT = 4;

// p8 final (M-1): what app/chat/loading.tsx shows while the chat segment loads — shaped like
// `ChatWelcome` (the empty-state prompt ChatScreen renders once mounted) so nothing jumps when
// the real screen lands: a title line, a description line, a wrapping row of suggested-question
// placeholders, then the composer block at the bottom.
export default function Component() {
  return (
    <Box role="status" aria-label={LOADING_LABEL}>
      <Skeleton variant="text" width="40%" height={44} />
      <Skeleton variant="text" width="70%" />
      <Stack direction="row" useFlexGap spacing={1} sx={{ flexWrap: 'wrap', mt: 2, mb: 4 }}>
        {Array.from({ length: SUGGESTED_QUESTION_COUNT }, (_, index) => (
          <Skeleton key={index} variant="rounded" width={140} height={40} />
        ))}
      </Stack>
      <Skeleton variant="rounded" height={56} />
    </Box>
  );
}
