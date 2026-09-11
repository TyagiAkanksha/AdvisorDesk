'use client';

import { Box, Chip, Link } from '@/components/common';

import type { TagChipsProps } from './interface';

// p8 final (I-2, DESIGN.md §B3): the article's tag chips now navigate client-side like every
// other tag chip on the site (`ArticleCard`, `TagFilter`) instead of a plain `<a>` full
// navigation. `common/Link` is a `'use client'` module, so its export is a client reference and
// may be passed as `component=` from a Server Component; this leaf is a client component because
// it *uses* the browser (next/link's client-side routing), not because the prop itself can't
// cross the RSC boundary — see `ArticleScreen/Component.tsx`'s header comment.
export default function Component({ tags }: TagChipsProps) {
  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
      {tags.map((tag) => (
        <Chip<typeof Link>
          key={tag}
          component={Link}
          href={`/?tag=${encodeURIComponent(tag)}`}
          clickable
          label={tag}
          variant="outlined"
        />
      ))}
    </Box>
  );
}
