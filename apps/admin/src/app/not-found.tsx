import { Box, Button, PageContainer, Paper, Typography } from '@/components/common';
import { BACK_TO_DASHBOARD_LABEL, NOT_FOUND_MESSAGE, NOT_FOUND_TITLE } from '@/lib/copy';

// phase-8 task-07 (DESIGN.md §A4). Root-level not-found handles every unmatched URL and renders
// under the root layout only (no AppShell — route groups don't wrap unmatched URLs), hence the
// self-contained card.
// phase-8 task-15 (DESIGN.md §C1): `PageContainer` no longer renders a `<main>` (AppShell now
// owns the page's one `<main>` landmark) — this unframed route supplies its own so it still
// keeps a main landmark.
export default function NotFound() {
  return (
    <Box component="main" sx={{ py: 4 }}>
      <PageContainer>
        <Paper variant="outlined" sx={{ p: 4, maxWidth: 480, mx: 'auto', mt: 8 }}>
          <Typography variant="h1" component="h1" gutterBottom>
            {NOT_FOUND_TITLE}
          </Typography>
          <Typography component="p" sx={{ mb: 3 }}>
            {NOT_FOUND_MESSAGE}
          </Typography>
          <Button href="/" variant="outlined">
            {BACK_TO_DASHBOARD_LABEL}
          </Button>
        </Paper>
      </PageContainer>
    </Box>
  );
}
