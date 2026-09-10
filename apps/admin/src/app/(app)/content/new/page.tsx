import type { Metadata } from 'next';

import { PageContainer } from '@/components/common';
import { ContentEditorScreen } from '@/components/content/ContentEditorScreen';

export const metadata: Metadata = { title: 'New content' };

export default function Page() {
  return (
    <PageContainer>
      <ContentEditorScreen />
    </PageContainer>
  );
}
