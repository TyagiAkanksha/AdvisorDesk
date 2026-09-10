import type { Metadata } from 'next';

import { PageContainer } from '@/components/common';
import { ContentListScreen } from '@/components/content/ContentListScreen';

export const metadata: Metadata = { title: 'Content' };

export default function Page() {
  return (
    <PageContainer>
      <ContentListScreen />
    </PageContainer>
  );
}
