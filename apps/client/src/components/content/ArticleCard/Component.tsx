'use client';

import { Card, Link, Typography } from '@/components/common';
import { formatPublishedDate } from '@/lib/formatDate';

import { TagChips } from '../TagChips';
import type { ArticleCardProps } from './interface';

// phase-8 task-09 (DESIGN.md §B2): one article summary card, equal height in a grid. The tag
// chips are the shared `TagChips` client leaf (p8 t24); the title link is `common/Link`, a
// `'use client'` module whose export is a client reference — this card stays a client leaf
// because it uses next/link's client-side routing, not because a prop cannot cross the RSC
// boundary (see `ArticleScreen/Component.tsx`'s header comment for the corrected rule).
//
// p8 t24: `titleAs` (default 'h2') lets `RelatedArticles` render the card title as an h3 under
// its own section h2, instead of a second competing h2 on the page. The Typography keeps
// `variant="h4"` either way — only the heading level (`component`) changes.
export default function Component({ item, titleAs = 'h2' }: ArticleCardProps) {
  return (
    <Card sx={{ height: '100%' }}>
      <Typography variant="h4" component={titleAs} gutterBottom>
        <Link href={`/content/${item.slug}`} underline="hover" color="inherit">
          {item.title}
        </Link>
      </Typography>
      <Typography variant="body2" color="text.secondary" component="p" sx={{ mb: 1.5 }}>
        {formatPublishedDate(item.published_at)}
      </Typography>
      <TagChips tags={item.tags} />
    </Card>
  );
}
