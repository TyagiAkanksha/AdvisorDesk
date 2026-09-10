import { Box, Link, Typography } from '@/components/common';
import { SOURCES_LABEL } from '@/lib/copy';

import type { CitationListProps } from './interface';

// phase-8 task-12 (DESIGN.md §B4). Sources: a titled list of real links, numbered in server
// order — a reader no longer has to hover a `[n]` chip to learn what it cites. `citations`
// arrives already deduped-and-ordered by the server (`app.rag.synthesis.dedupe_citations`);
// `index` here is purely display numbering, never a re-sort key. Renders nothing for an empty
// array (the refusal case — `MessageBubble` owns showing that distinctly via its own alert).
export default function Component({ citations }: CitationListProps) {
  if (citations.length === 0) {
    return null;
  }

  return (
    <nav aria-label={SOURCES_LABEL}>
      <Typography variant="overline" component="p">
        {SOURCES_LABEL}
      </Typography>
      <Box component="ol" sx={{ pl: 2.5, m: 0 }}>
        {citations.map((citation, index) => (
          <li key={citation.content_id}>
            <Link href={`/content/${citation.slug}`}>
              [{index + 1}] {citation.title}
            </Link>
          </li>
        ))}
      </Box>
    </nav>
  );
}
