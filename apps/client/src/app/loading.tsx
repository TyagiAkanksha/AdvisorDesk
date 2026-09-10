import { PageContainer } from '@/components/common';
import { ContentListSkeleton } from '@/components/content/ContentListSkeleton';

// phase-8 task-07: Next renders this inside a Suspense boundary while the segment's RSC data
// loads (docs/FRONTEND-CONVENTIONS.md §9 — never a silent blank region).
export default function Loading() {
  return (
    <PageContainer>
      <ContentListSkeleton />
    </PageContainer>
  );
}
