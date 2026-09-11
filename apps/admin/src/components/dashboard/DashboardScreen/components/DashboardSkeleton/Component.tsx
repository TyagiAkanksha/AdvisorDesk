import { Box, Grid, Skeleton } from '@/components/common';
import { LOADING_LABEL } from '@/lib/copy';

// task-17 (DESIGN.md §2, §5 C3): a labelled skeleton (not a spinner) while `GET /stats` is
// pending with nothing cached — the shape mirrors the loaded screen's own Grid: three stat-card
// slots plus the two outlined panels.
export default function Component() {
  return (
    <Box role="status" aria-label={LOADING_LABEL}>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, sm: 4 }}>
          <Skeleton variant="rectangular" height={92} />
        </Grid>
        <Grid size={{ xs: 12, sm: 4 }}>
          <Skeleton variant="rectangular" height={92} />
        </Grid>
        <Grid size={{ xs: 12, sm: 4 }}>
          <Skeleton variant="rectangular" height={92} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Skeleton variant="rectangular" height={240} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Skeleton variant="rectangular" height={240} />
        </Grid>
      </Grid>
    </Box>
  );
}
