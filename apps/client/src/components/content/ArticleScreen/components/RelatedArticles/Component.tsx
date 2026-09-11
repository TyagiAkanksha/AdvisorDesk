import { Grid, Typography } from '@/components/common';
import { RELATED_ARTICLES_TITLE } from '@/lib/copy';

import { ArticleCard } from '../../../ArticleCard';
import type { RelatedArticlesProps } from './interface';

// phase-8 task-10 (DESIGN.md §B3): up to three related summaries reusing the home page's card.
export default function Component({ items }: RelatedArticlesProps) {
  if (items.length === 0) {
    return null;
  }

  return (
    <Grid
      container
      spacing={2}
      component="section"
      aria-labelledby="related-articles-heading"
      sx={{ mt: 4 }}
    >
      <Grid size={12}>
        <Typography variant="h3" component="h2" id="related-articles-heading">
          {RELATED_ARTICLES_TITLE}
        </Typography>
      </Grid>
      {items.map((item) => (
        <Grid key={item.slug} size={{ xs: 12, sm: 4 }}>
          <ArticleCard item={item} />
        </Grid>
      ))}
    </Grid>
  );
}
