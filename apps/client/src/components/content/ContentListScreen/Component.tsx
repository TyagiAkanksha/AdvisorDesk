import { Button, EmptyState, Grid, Stack, Typography } from '@/components/common';
import {
  HOME_CTA_LABEL,
  HOME_DESCRIPTION,
  HOME_TITLE,
  NO_CONTENT_MESSAGE,
  noArticlesTaggedMessage,
  SHOW_ALL_LABEL,
} from '@/lib/copy';

import { ArticleCard } from '../ArticleCard';
import { TagFilter } from './components/TagFilter';
import type { ContentListScreenProps } from './interface';

// phase-8 task-09 (DESIGN.md §B2), PRD §2.2 ("As a client, I can browse published content").
// Dumb, synchronous — `items`/`tags`/`selectedTag` arrive already fetched and filtered by the
// thin async page (docs/FRONTEND-CONVENTIONS.md §6, RSC data fetching). Owns the page header
// (h1 + description + the single gold CTA), the tag filter, the responsive grid, and the two
// empty states (no content at all vs. a tag with no matches).
export default function Component({ items, tags, selectedTag }: ContentListScreenProps) {
  return (
    <div>
      {/* MUI 9.2's `StackOwnProps` has no top-level `justifyContent`/`alignItems` (only
          `direction`/`spacing`/`divider`/`useFlexGap`/`sx` — verified against
          node_modules/@mui/material/Stack/Stack.d.ts); the brief's `justifyContent`/`alignItems`
          props go through `sx` instead, same rendered flexbox layout. */}
      {/* p8 final (M-4): stretched alignItems made the gold CTA button full-bleed on phones
          (column layout) — pin the xs value to flex-start so it hugs its own width there too. */}
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={2}
        sx={{
          mb: 3,
          justifyContent: 'space-between',
          alignItems: { xs: 'flex-start', sm: 'center' },
        }}
      >
        <div>
          <Typography variant="h1">{HOME_TITLE}</Typography>
          <Typography variant="body1" color="text.secondary">
            {HOME_DESCRIPTION}
          </Typography>
        </div>
        <Button variant="contained" color="secondary" href="/chat">
          {HOME_CTA_LABEL}
        </Button>
      </Stack>

      {tags.length > 0 ? <TagFilter tags={tags} selectedTag={selectedTag} /> : null}

      {items.length === 0 && selectedTag === null ? (
        <EmptyState message={NO_CONTENT_MESSAGE} />
      ) : items.length === 0 && selectedTag !== null ? (
        <EmptyState
          icon="Search"
          message={noArticlesTaggedMessage(selectedTag)}
          action={{ label: SHOW_ALL_LABEL, href: '/' }}
        />
      ) : (
        <Grid container spacing={2}>
          {items.map((item) => (
            <Grid key={item.slug} size={{ xs: 12, sm: 6, md: 4 }}>
              <ArticleCard item={item} />
            </Grid>
          ))}
        </Grid>
      )}
    </div>
  );
}
