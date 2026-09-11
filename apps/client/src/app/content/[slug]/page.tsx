import type { Metadata } from 'next';
import { notFound } from 'next/navigation';

import { PageContainer } from '@/components/common';
import { ArticleScreen } from '@/components/content/ArticleScreen';
import { getContentBySlug, getPublishedContent } from '@/lib/publicApi';
import { relatedArticles } from '@/lib/related';

interface PageProps {
  params: Promise<{ slug: string }>;
}

// task-04, PRD §2.2/§12 (titles-only SEO). A deleted/unknown slug 404s via Next's own not-found
// page — never our own error UI (PRD §5.3: "a deleted item's slug 404s and is never
// reassigned"). `getContentBySlug` is `cache()`-wrapped (src/lib/publicApi.ts), so this call and
// the page's own call below dedupe to one fetch per request.
export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const article = await getContentBySlug(slug);

  if (!article) {
    return { title: 'Not found' };
  }
  return { title: article.title };
}

// phase-8 task-10 (DESIGN.md §B3): `md`-width reading column plus up to three related articles
// computed from the full published list (`relatedArticles` — src/lib/related.ts). Thin: fetching
// and 404 handling only, no layout/markup of its own.
export default async function Page({ params }: PageProps) {
  const { slug } = await params;
  const [article, all] = await Promise.all([getContentBySlug(slug), getPublishedContent()]);

  if (!article) {
    notFound();
  }

  return (
    <PageContainer maxWidth="md">
      <ArticleScreen article={article} related={relatedArticles(all, article)} />
    </PageContainer>
  );
}
