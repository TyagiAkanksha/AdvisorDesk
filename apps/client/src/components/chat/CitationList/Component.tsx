import { Link } from '@/components/common';

import type { CitationListProps } from './interface';

// task-05 (phase-4), PRD §5.3. Dumb, pure list renderer — each chip's accessible name is its
// `[n]` numbering text alone (test-author judgment call, `p4-t05-test-author.md`); `citations`
// is already deduped-and-ordered by the server, so `index` here is purely display numbering,
// never a re-sort key. Renders nothing for an empty array (the refusal case — `MessageBubble`
// owns showing that distinctly via `role="status"`, not this component).
export default function Component({ citations }: CitationListProps) {
  if (citations.length === 0) {
    return null;
  }

  return (
    <nav aria-label="Citations">
      {citations.map((citation, index) => (
        <Link key={citation.content_id} href={`/content/${citation.slug}`} sx={{ mr: 1 }}>
          {`[${index + 1}]`}
        </Link>
      ))}
    </nav>
  );
}
