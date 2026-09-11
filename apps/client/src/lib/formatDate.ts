// task-04 fix round 1 (F5): corrected — only `ArticleScreen` renders a date today
// (`ContentListScreen` shows title/tags per card, no date). Same 'en-US' short-month format as
// apps/admin/src/components/content/ContentListScreen/components/ContentTable/Component.tsx's
// `formatUpdatedAt`. Kept as its own `lib/` function rather than inlined into `ArticleScreen`:
// it's a pure formatting rule (not view logic) and a second call site (e.g. a future
// `ContentListScreen` date) is a one-line addition away, not a refactor.
//
// phase-8 task-09 fix: `timeZone: 'UTC'` pinned so the rendered day matches the ISO date the API
// sent regardless of the viewer's/test runner's local clock. Without it, a midnight-UTC
// `published_at` (every seed value in this codebase) rolls back a calendar day in any timezone
// west of UTC — reproduced in isolation: `ArticleCard`'s authored test (`'2026-01-15T00:00:00Z'`
// → `'Jan 15, 2026'`) failed only under this host's local America/New_York timezone and passed
// unmodified under `TZ=UTC`; GitHub Actions' `ubuntu-latest` runners default to UTC, so CI was
// never exposed to this. `ArticleScreen`'s existing test predates this fix and already worked
// around the same root cause by asserting only that the year is visible, not the exact string
// (see that file's `it('renders the published date visibly', ...)` comment) — this fix makes
// that workaround unnecessary going forward without weakening it.
export function formatPublishedDate(value: string): string {
  return new Date(value).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  });
}
