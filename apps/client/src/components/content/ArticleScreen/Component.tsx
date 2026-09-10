import { Alert, Box, Button, Chip, Divider, Link, Typography } from '@/components/common';
import { ASK_ABOUT_TOPIC_LABEL, BACK_TO_ARTICLES_LABEL, DISCLAIMER } from '@/lib/copy';
import { formatPublishedDate } from '@/lib/formatDate';
import { stripLeadingHeading } from '@/lib/markdown';

import { Markdown } from '../Markdown';
import { RelatedArticles } from './components/RelatedArticles';
import type { ArticleScreenProps } from './interface';

// PRD §2.2 (detail renders markdown) + §8 (disclaimer). Dumb, synchronous — `article` and
// `related` arrive from the thin async page. phase-8 task-10 (DESIGN.md §B3): reading layout —
// back link, meta line with tag links, one h1 (body `#` stripped, `##` demoted to h3), the
// disclaimer as an outlined info alert, related articles, and a CTA into chat.
export default function Component({ article, related }: ArticleScreenProps) {
  return (
    <article>
      <Link href="/" underline="hover" sx={{ display: 'inline-block', mb: 2 }}>
        ← {BACK_TO_ARTICLES_LABEL}
      </Link>
      <Typography variant="h1" component="h1" gutterBottom>
        {article.title}
      </Typography>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1, mb: 2 }}>
        <Typography variant="body2" color="text.secondary" component="p">
          {formatPublishedDate(article.published_at)}
        </Typography>
        {article.tags.map((tag) => (
          <Chip<'a'>
            key={tag}
            component="a"
            href={`/?tag=${encodeURIComponent(tag)}`}
            clickable
            label={tag}
            variant="outlined"
          />
        ))}
      </Box>
      <Divider sx={{ mb: 3 }} />
      <Markdown markdown={stripLeadingHeading(article.body_md, article.title)} headingOffset={1} />
      <Alert severity="info" variant="outlined" sx={{ mt: 4 }}>
        {DISCLAIMER}
      </Alert>
      <RelatedArticles items={related} />
      <Box sx={{ mt: 4 }}>
        <Button variant="outlined" href="/chat">
          {ASK_ABOUT_TOPIC_LABEL}
        </Button>
      </Box>
    </article>
  );
}
