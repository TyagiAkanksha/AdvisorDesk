import { Box, Grid, Skeleton } from '@/components/common';
import { LOADING_LABEL } from '@/lib/copy';

const PLACEHOLDER_COUNT = 6;

// phase-8 task-09 (DESIGN.md §B2): what app/loading.tsx shows while the RSC list fetch is in
// flight — matches ContentListScreen's header + responsive card grid so nothing jumps when data
// lands.
export default function Component() {
  return (
    <Box role="status" aria-label={LOADING_LABEL}>
      <Skeleton variant="text" width="30%" height={44} sx={{ mb: 3 }} />
      <Grid container spacing={2}>
        {Array.from({ length: PLACEHOLDER_COUNT }, (_, index) => (
          <Grid key={index} size={{ xs: 12, sm: 6, md: 4 }}>
            <Skeleton variant="rounded" height={140} />
          </Grid>
        ))}
      </Grid>
    </Box>
  );
}
