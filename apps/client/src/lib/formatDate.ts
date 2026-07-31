// Shared by ContentListScreen and ArticleScreen (both render `published_at`) — same 'en-US'
// short-month format as apps/admin/src/components/content/ContentListScreen/components/
// ContentTable/Component.tsx's `formatUpdatedAt`, kept as one function here since both client
// call sites need it (unlike the admin file, which has exactly one).
export function formatPublishedDate(value: string): string {
  return new Date(value).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}
