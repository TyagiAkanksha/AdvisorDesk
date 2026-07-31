import { Card, Chip, EmptyState, Link, Typography } from '@/components/common';

import type { ContentListScreenProps } from './interface';

// task-04 (phase-3), PRD §2.2 ("As a client, I can browse published content"). Dumb, synchronous
// — `items` arrives already fetched from the thin async page via `src/lib/publicApi.ts`
// (docs/FRONTEND-CONVENTIONS.md §6, RSC data fetching). Each card links to `/content/{slug}` —
// the exact route shape phase-4's citation links target.
export default function Component({ items }: ContentListScreenProps) {
  if (items.length === 0) {
    return <EmptyState message="No published content yet." />;
  }

  return (
    <div>
      {items.map((item) => (
        <Card key={item.slug} sx={{ mb: 2 }}>
          <Typography variant="h6" component="h2" gutterBottom>
            <Link href={`/content/${item.slug}`}>{item.title}</Link>
          </Typography>
          <div>
            {item.tags.map((tag) => (
              <Chip key={tag} label={tag} size="small" sx={{ mr: 0.5 }} />
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}
