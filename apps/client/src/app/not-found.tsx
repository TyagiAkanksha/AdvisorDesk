import { Button, PageContainer, Typography } from '@/components/common';
import { BACK_TO_ARTICLES_LABEL, NOT_FOUND_MESSAGE, NOT_FOUND_TITLE } from '@/lib/copy';

// phase-8 task-07 (DESIGN.md §A4): Next's default 404 is a black full-screen page — off-brand for
// a navy/gold content site. Root-level, so it handles every unmatched URL and `notFound()` calls.
export default function NotFound() {
  return (
    <PageContainer maxWidth="sm">
      <Typography variant="h1" component="h1" gutterBottom>
        {NOT_FOUND_TITLE}
      </Typography>
      <Typography component="p" sx={{ mb: 3 }}>
        {NOT_FOUND_MESSAGE}
      </Typography>
      <Button href="/" variant="outlined">
        {BACK_TO_ARTICLES_LABEL}
      </Button>
    </PageContainer>
  );
}
