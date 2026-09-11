import type { Metadata } from 'next';
import { Suspense } from 'react';

import { PageContainer } from '@/components/common';
import { ContentListScreen } from '@/components/content/ContentListScreen';
import { PageSkeleton } from '@/components/shell/PageSkeleton';

export const metadata: Metadata = { title: 'Content' };

// phase-8 task-18: the screen reads `useSearchParams()`; Next requires a Suspense boundary above
// any such client component on a statically prerendered route (build error otherwise).
export default function Page() {
  return (
    <PageContainer>
      <Suspense fallback={<PageSkeleton />}>
        <ContentListScreen />
      </Suspense>
    </PageContainer>
  );
}
