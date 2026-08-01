import { Link, PageContainer, Typography } from '@/components/common';
import { ContentListScreen } from '@/components/content/ContentListScreen';
import { getPublishedContent } from '@/lib/publicApi';

// task-04: the phase-1 placeholder becomes the real content list page (PRD §2.2). RSC — fetches
// server-side, no client JS needed for the initial render (docs/FRONTEND-CONVENTIONS.md §6).
//
// task-05 (phase-4): the nav link to `/chat` lives HERE, not inside `ContentListScreen` itself —
// that component's own pinned test (`ContentListScreen/Component.test.tsx`, "shows a visible,
// non-empty empty-state message for an empty items list") asserts `queryByRole('link')` is
// absent for an empty item list, so a link baked into that component would always render and
// break that pin. `Link` is already a client-boundary leaf (`common/Link/Component.tsx`'s own
// `'use client'`), so an RSC page can render it directly with no boundary issue.
export default async function Page() {
  const items = await getPublishedContent();

  return (
    <PageContainer>
      <Typography component="nav" variant="body2" sx={{ mb: 2 }}>
        <Link href="/chat">Ask a question</Link>
      </Typography>
      <ContentListScreen items={items} />
    </PageContainer>
  );
}
