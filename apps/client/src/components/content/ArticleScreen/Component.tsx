import { Chip, Typography } from '@/components/common';
import { DISCLAIMER } from '@/lib/copy';
import { formatPublishedDate } from '@/lib/formatDate';
import { stripLeadingHeading } from '@/lib/markdown';

import { Markdown } from '../Markdown';
import type { ArticleScreenProps } from './interface';

// task-04 (phase-3), PRD §2.2 (detail page renders markdown) + §8. Dumb, synchronous —
// `article` arrives already fetched from the thin async page via `src/lib/publicApi.ts`.
export default function Component({ article }: ArticleScreenProps) {
  return (
    <article>
      <Typography variant="h1" component="h1" gutterBottom>
        {article.title}
      </Typography>
      <Typography variant="body2" color="text.secondary" component="p">
        {formatPublishedDate(article.published_at)}
      </Typography>
      <div>
        {article.tags.map((tag) => (
          <Chip key={tag} label={tag} size="small" sx={{ mr: 0.5, mb: 2 }} />
        ))}
      </div>
      <Markdown markdown={stripLeadingHeading(article.body_md, article.title)} headingOffset={1} />
      <Typography
        variant="body2"
        color="text.secondary"
        component="footer"
        sx={{ mt: 4, pt: 2, borderTop: 1, borderColor: 'divider' }}
      >
        {DISCLAIMER}
      </Typography>
    </article>
  );
}
