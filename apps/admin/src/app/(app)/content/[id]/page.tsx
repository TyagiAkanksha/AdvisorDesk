import type { Metadata } from 'next';

import { PageContainer } from '@/components/common';
import { ContentEditorScreen } from '@/components/content/ContentEditorScreen';

interface PageProps {
  params: Promise<{ id: string }>;
}

export const metadata: Metadata = { title: 'Edit content' };

export default async function Page({ params }: PageProps) {
  const { id } = await params;

  return (
    <PageContainer>
      <ContentEditorScreen contentId={id} />
    </PageContainer>
  );
}
