// fix round 1, F3 (controller-resolved plan conflict): the brief's Goal calls for
// "status/tag counts from GET /stats" — only `by_status` shipped. Dumb per
// docs/FRONTEND-CONVENTIONS.md §3: `by_tag` entries in, no fetching here.
export interface TagCountsProps {
  byTag: Record<string, number>;
}
