import { PageContainer } from '@/components/common';
import { ContentEditorScreen } from '@/components/content/ContentEditorScreen';

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function Page({ params }: PageProps) {
  const { id } = await params;

  return (
    <PageContainer>
      <ContentEditorScreen contentId={id} />
    </PageContainer>
  );
}
