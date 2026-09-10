import { Box, Skeleton } from '@/components/common';

const LINE_COUNT = 8;

export default function Component() {
  return (
    <Box role="status" aria-label="Loading">
      <Skeleton variant="text" width="70%" height={44} />
      <Skeleton variant="text" width="25%" sx={{ mb: 3 }} />
      {Array.from({ length: LINE_COUNT }, (_, index) => (
        <Skeleton key={index} variant="text" width={index % 3 === 2 ? '80%' : '100%'} />
      ))}
    </Box>
  );
}
