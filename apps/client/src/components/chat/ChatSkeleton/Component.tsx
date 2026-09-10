import { Box, Skeleton } from '@/components/common';
import { LOADING_LABEL } from '@/lib/copy';

const MESSAGE_COUNT = 3;

// p8 final: what app/chat/loading.tsx shows while the chat segment loads — a heading-sized line
// (the empty-state prompt ChatScreen renders once mounted) above a stack of message-shaped
// blocks, so nothing jumps when the real screen lands.
export default function Component() {
  return (
    <Box role="status" aria-label={LOADING_LABEL}>
      <Skeleton variant="text" width="40%" height={40} />
      {Array.from({ length: MESSAGE_COUNT }, (_, index) => (
        <Skeleton key={index} variant="rounded" height={56} sx={{ mb: 2 }} />
      ))}
    </Box>
  );
}
