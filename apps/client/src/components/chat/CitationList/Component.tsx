import { Box, Link, Typography } from '@/components/common';
import { SOURCES_LABEL } from '@/lib/copy';

import type { CitationListProps } from './interface';

// phase-8 task-12 (DESIGN.md §B4). Sources: a titled list of real links, numbered in server
// order — a reader no longer has to hover a `[n]` chip to learn what it cites. `citations`
// arrives already deduped-and-ordered by the server (`app.rag.synthesis.dedupe_citations`);
// `index` here is purely display numbering, never a re-sort key. Renders nothing for an empty
// array (the refusal case — `MessageBubble` owns showing that distinctly via its own alert).
//
// fix round 1, I-1: the browser's own `<ol>` decimal marker was doubling up with our own
// `[n]` prefix ("1. [1] Homeowners Liability Basics") — `listStyleType: 'none'` (not the
// `listStyle` shorthand, which also touches position/image we don't need to reset) suppresses
// just the marker; `pl: 0` removes the indent that marker used to occupy.
//
// p8 t24 (DESIGN.md §B4 carry-in): a `<section>` (ARIA `region`), not a `<nav>` — `nav` is for
// site navigation; one message's citation list is content, so it is a named region (one per
// answer, which is fine for a region).
export default function Component({ citations }: CitationListProps) {
  if (citations.length === 0) {
    return null;
  }

  return (
    <Box component="section" aria-label={SOURCES_LABEL}>
      <Typography variant="overline" component="p">
        {SOURCES_LABEL}
      </Typography>
      <Box component="ol" sx={{ listStyleType: 'none', pl: 0, m: 0 }}>
        {citations.map((citation, index) => (
          <li key={citation.content_id}>
            <Link href={`/content/${citation.slug}`}>
              [{index + 1}] {citation.title}
            </Link>
          </li>
        ))}
      </Box>
    </Box>
  );
}
