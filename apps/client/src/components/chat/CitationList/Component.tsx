import { Chip } from '@/components/common';

import type { CitationListProps } from './interface';

// task-05 (phase-4), PRD §5.3. Dumb, pure list renderer — each chip's accessible name is its
// `[n]` numbering text alone (test-author judgment call, `p4-t05-test-author.md`); `citations`
// is already deduped-and-ordered by the server, so `index` here is purely display numbering,
// never a re-sort key. Renders nothing for an empty array (the refusal case — `MessageBubble`
// owns showing that distinctly via `role="status"`, not this component).
//
// task-05 review round 1 (M-1, M-2): each citation now renders as a REAL `common/Chip`
// (previously an unadorned `common/Link`, leaving `common/Chip` unused despite the brief's own
// "numbered `[n]` chips" wording) rendered AS a link — `component="a"` + `href` + `clickable`
// (MUI's own documented pattern for "an anchor Chip is clickable"; verified empirically to
// render a real `<a href>` with native `role="link"`, not `role="button"` via `ButtonBase`) —
// so it keeps the pinned `role="link"`/`toHaveAccessibleName('[n]')`/`href` contract exactly.
// `title={citation.title}` (WCAG 2.4.4, "Link Purpose") surfaces the article title as a tooltip;
// the chip's visible content ('[n]') still wins the accessible-name computation over `title`, so
// the pin is unaffected.
export default function Component({ citations }: CitationListProps) {
  if (citations.length === 0) {
    return null;
  }

  return (
    <nav aria-label="Citations">
      {citations.map((citation, index) => (
        <Chip<'a'>
          key={citation.content_id}
          component="a"
          href={`/content/${citation.slug}`}
          title={citation.title}
          clickable
          size="small"
          label={`[${index + 1}]`}
          sx={{ mr: 1, mb: 0.5 }}
        />
      ))}
    </nav>
  );
}
