import type { PublicContentSummary } from '@/types';

const DEFAULT_MAX = 3;

function sharedTagCount(a: readonly string[], b: readonly string[]): number {
  return a.filter((tag) => b.includes(tag)).length;
}

// phase-8 task-10 (DESIGN.md §B3). Pure: same-tag articles first (most shared tags, then most
// recent), then the most recent others if needed to reach `max`. The public list endpoint has no
// "related" query, and 30 summaries sort in microseconds — a request would cost more than it saves.
export function relatedArticles(
  all: PublicContentSummary[],
  current: Pick<PublicContentSummary, 'slug' | 'tags'>,
  max = DEFAULT_MAX,
): PublicContentSummary[] {
  return all
    .filter((item) => item.slug !== current.slug)
    .map((item) => ({ item, shared: sharedTagCount(item.tags, current.tags) }))
    .sort((a, b) => b.shared - a.shared || b.item.published_at.localeCompare(a.item.published_at))
    .slice(0, max)
    .map(({ item }) => item);
}
