import { Chip, Typography } from '@/components/common';
import { formatPublishedDate } from '@/lib/formatDate';

import { Markdown } from '../Markdown';
import type { ArticleScreenProps } from './interface';

// PRD §8 (Seed data): the sample-content footer line. Rendered here unconditionally, on every
// article, independent of `body_md` — the seed pipeline that bakes this sentence into seeded
// articles' `body_md` doesn't exist until phase-4 (PRD §10), but task-04's own acceptance
// criterion ("Disclaimer footer visible on every article (§8)") holds today only if
// `ArticleScreen` supplies it itself. Verbatim PRD wording (controller-confirmed, test-author
// report ambiguity #1) — do not source this from content data.
const DISCLAIMER = 'Sample content for demonstration purposes — not financial advice.';

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
      <Markdown markdown={article.body_md} />
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
