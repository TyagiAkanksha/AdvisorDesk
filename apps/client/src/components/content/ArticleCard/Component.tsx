'use client';

import { Box, Card, Chip, Link, Typography } from '@/components/common';
import { formatPublishedDate } from '@/lib/formatDate';

import type { ArticleCardProps } from './interface';

// phase-8 task-09 (DESIGN.md §B2): one article summary card, equal height in a grid. A client
// leaf because the tag chips render through `common/Link` (next/link) as `component` — a
// function prop that cannot cross the RSC boundary from a Server Component parent.
export default function Component({ item }: ArticleCardProps) {
  return (
    <Card sx={{ height: '100%' }}>
      <Typography variant="h4" component="h2" gutterBottom>
        <Link href={`/content/${item.slug}`} underline="hover" color="inherit">
          {item.title}
        </Link>
      </Typography>
      <Typography variant="body2" color="text.secondary" component="p" sx={{ mb: 1.5 }}>
        {formatPublishedDate(item.published_at)}
      </Typography>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
        {item.tags.map((tag) => (
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
    </Card>
  );
}
