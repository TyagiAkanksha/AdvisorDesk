import { Box, Grid, Skeleton, Stack } from '@/components/common';
import { LOADING_LABEL } from '@/lib/copy';

// phase-8 task-20 (DESIGN.md §5 C5, "Loading states"): an editor-shaped skeleton (title bar,
// two-column form/preview) instead of a spinner — `role="status"` so assistive tech announces
// it once, with no `progressbar` role anywhere in the tree.
export default function Component() {
  return (
    <Box role="status" aria-label={LOADING_LABEL}>
      <Skeleton variant="text" width="40%" height={40} sx={{ mb: 3 }} />
      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 7 }}>
          <Stack spacing={2}>
            <Skeleton variant="rectangular" height={40} />
            <Skeleton variant="rectangular" height={320} />
            <Skeleton variant="rectangular" height={40} />
          </Stack>
        </Grid>
        <Grid size={{ xs: 12, md: 5 }}>
          <Skeleton variant="rectangular" height={400} />
        </Grid>
      </Grid>
    </Box>
  );
}
