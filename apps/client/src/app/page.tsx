import { PageContainer } from '@/components/common';
import { ContentListScreen } from '@/components/content/ContentListScreen';
import { filterByTag, uniqueTags } from '@/lib/filterByTag';
import { getPublishedContent } from '@/lib/publicApi';

interface PageProps {
  searchParams: Promise<{ tag?: string }>;
}

// PRD §2.2 browse. RSC: fetch + filter server-side from `?tag=` (docs/FRONTEND-CONVENTIONS.md §6)
// so the URL is the filter state — shareable, no client island for the list itself.
export default async function Page({ searchParams }: PageProps) {
  const { tag } = await searchParams;
  const selectedTag = tag && tag.length > 0 ? tag : null;
  const items = await getPublishedContent();

  return (
    <PageContainer>
      <ContentListScreen
        items={filterByTag(items, selectedTag)}
        tags={uniqueTags(items)}
        selectedTag={selectedTag}
      />
    </PageContainer>
  );
}
