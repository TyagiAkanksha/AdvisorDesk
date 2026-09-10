import { Box, Skeleton, Stack } from '@/components/common';
import { LOADING_LABEL } from '@/lib/copy';

const ROW_COUNT = 5;

export default function Component() {
  return (
    <Box role="status" aria-label={LOADING_LABEL}>
      <Skeleton variant="text" width="30%" height={40} sx={{ mb: 3 }} />
      <Stack spacing={1.5}>
        {Array.from({ length: ROW_COUNT }, (_, index) => (
          <Skeleton key={index} variant="rectangular" height={48} />
        ))}
      </Stack>
    </Box>
  );
}
