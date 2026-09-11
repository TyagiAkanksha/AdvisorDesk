import type { PublicContentSummary } from '@/types';

// phase-8 task-09 (DESIGN.md §B2): pure helpers behind the home page's `?tag=` filter — kept out
// of the RSC page/screen so they're testable in isolation (node env, no DOM).

/** Unique tags across `items`, sorted A→Z (locale-insensitive, plain `<`). */
export function uniqueTags(items: PublicContentSummary[]): string[] {
  const tags = new Set<string>();
  for (const item of items) {
    for (const tag of item.tags) {
      tags.add(tag);
    }
  }
  return Array.from(tags).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
}

/** `tag === null` → `items` unchanged; otherwise only items whose `tags` include `tag` (exact match). */
export function filterByTag(
  items: PublicContentSummary[],
  tag: string | null,
): PublicContentSummary[] {
  if (tag === null) {
    return items;
  }
  return items.filter((item) => item.tags.includes(tag));
}
