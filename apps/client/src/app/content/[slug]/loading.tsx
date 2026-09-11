import { PageContainer } from '@/components/common';
import { ArticleSkeleton } from '@/components/content/ArticleSkeleton';

// phase-8 task-07: Next renders this inside a Suspense boundary while the segment's RSC data
// loads (docs/FRONTEND-CONVENTIONS.md §9 — never a silent blank region).
export default function Loading() {
  return (
    <PageContainer maxWidth="md">
      <ArticleSkeleton />
    </PageContainer>
  );
}
