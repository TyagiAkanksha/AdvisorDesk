// fix round 1, F4: order-INsensitive — the server always returns `tags` sorted alphabetically
// (app.services.tags), while the client appends newly-typed tags at the end of the array, so a
// positional comparison went false-not-equal for same-membership tag sets in a different order
// (phantom dirty: Save never re-disabled after a refetch echoed the sorted list back). Compare
// sorted copies; the array actually SENT to the server (`tags`, untouched) still preserves the
// user's own order.
export function tagsEqual(a: string[], b: string[]): boolean {
  if (a.length !== b.length) {
    return false;
  }
  const sortedA = [...a].sort();
  const sortedB = [...b].sort();
  return sortedA.every((value, index) => value === sortedB[index]);
}

// Mirrors app.services.tags._normalize_tag_name (PRD §4.1: lowercase, hyphenated) so a tag
// typed here matches what the server would store — any run of non-`[a-z0-9]` characters
// collapses to one hyphen, leading/trailing hyphens are stripped.
export function normalizeTag(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}
