import type { Metadata } from 'next';
import { notFound } from 'next/navigation';

import { PageContainer } from '@/components/common';
import { ArticleScreen } from '@/components/content/ArticleScreen';
import { getContentBySlug } from '@/lib/publicApi';

interface PageProps {
  params: Promise<{ slug: string }>;
}

// task-04, PRD §2.2/§12 (titles-only SEO). A deleted/unknown slug 404s via Next's own not-found
// page — never our own error UI (PRD §5.3: "a deleted item's slug 404s and is never
// reassigned").
export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const article = await getContentBySlug(slug);

  if (!article) {
    return { title: 'Not found' };
  }
  return { title: article.title };
}

export default async function Page({ params }: PageProps) {
  const { slug } = await params;
  const article = await getContentBySlug(slug);

  if (!article) {
    notFound();
  }

  return (
    <PageContainer>
      <ArticleScreen article={article} />
    </PageContainer>
  );
}
