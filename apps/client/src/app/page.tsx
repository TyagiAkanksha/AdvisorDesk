import { PageContainer } from '@/components/common';
import { ContentListScreen } from '@/components/content/ContentListScreen';
import { filterByTag, uniqueTags } from '@/lib/filterByTag';
import { getPublishedContent } from '@/lib/publicApi';

interface PageProps {
  searchParams: Promise<{ tag?: string | string[] }>;
}

// PRD §2.2 browse. RSC: fetch + filter server-side from `?tag=` (docs/FRONTEND-CONVENTIONS.md §6)
// so the URL is the filter state — shareable, no client island for the list itself.
//
// p8 t24: `?tag=` repeated in the URL (`?tag=a&tag=a`) parses to a `string[]` in Next's
// `searchParams`, not a `string` — treated the same as absent rather than crashing on
// `tag.length` (a `string[]`'s `.length` is its element count, not a character count, so the old
// check silently "worked" on a two-element array but for the wrong reason).
export default async function Page({ searchParams }: PageProps) {
  const { tag } = await searchParams;
  const selectedTag = typeof tag === 'string' && tag.length > 0 ? tag : null;
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
