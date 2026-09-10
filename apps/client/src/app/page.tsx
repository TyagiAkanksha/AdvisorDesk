import { PageContainer } from '@/components/common';
import { ContentListScreen } from '@/components/content/ContentListScreen';
import { getPublishedContent } from '@/lib/publicApi';

// task-04: the phase-1 placeholder becomes the real content list page (PRD §2.2). RSC — fetches
// server-side, no client JS needed for the initial render (docs/FRONTEND-CONVENTIONS.md §6).
export default async function Page() {
  const items = await getPublishedContent();

  return (
    <PageContainer>
      <ContentListScreen items={items} />
    </PageContainer>
  );
}
