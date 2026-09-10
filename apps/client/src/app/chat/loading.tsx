import { PageContainer } from '@/components/common';
import { ChatSkeleton } from '@/components/chat/ChatSkeleton';

// p8 final: Next renders this inside a Suspense boundary while the /chat segment loads
// (docs/FRONTEND-CONVENTIONS.md §9 — never a silent blank region), mirroring app/loading.tsx.
export default function Loading() {
  return (
    <PageContainer>
      <ChatSkeleton />
    </PageContainer>
  );
}
