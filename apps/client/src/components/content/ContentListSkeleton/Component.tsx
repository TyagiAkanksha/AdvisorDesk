import { Box, Skeleton } from '@/components/common';
import { LOADING_LABEL } from '@/lib/copy';

const PLACEHOLDER_COUNT = 6;

// phase-8 task-07: what app/loading.tsx shows while the RSC list fetch is in flight — the same
// footprint as the cards it replaces, so nothing jumps when data lands.
export default function Component() {
  return (
    <Box role="status" aria-label={LOADING_LABEL}>
      {Array.from({ length: PLACEHOLDER_COUNT }, (_, index) => (
        <Box key={index} sx={{ mb: 2, p: 2, border: 1, borderColor: 'divider', borderRadius: 1 }}>
          <Skeleton variant="text" width="60%" height={28} />
          <Skeleton variant="text" width="30%" />
        </Box>
      ))}
    </Box>
  );
}
