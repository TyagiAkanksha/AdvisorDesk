// task-04 fix round 1 (F5): corrected — only `ArticleScreen` renders a date today
// (`ContentListScreen` shows title/tags per card, no date). Same 'en-US' short-month format as
// apps/admin/src/components/content/ContentListScreen/components/ContentTable/Component.tsx's
// `formatUpdatedAt`. Kept as its own `lib/` function rather than inlined into `ArticleScreen`:
// it's a pure formatting rule (not view logic) and a second call site (e.g. a future
// `ContentListScreen` date) is a one-line addition away, not a refactor.
export function formatPublishedDate(value: string): string {
  return new Date(value).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}
