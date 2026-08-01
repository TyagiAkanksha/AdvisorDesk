import type { Metadata } from 'next';

import { PageContainer } from '@/components/common';
import { ChatScreen } from '@/components/chat/ChatScreen';

// task-05 (phase-4), PRD §2.2 ("As a client, I can ask the assistant a question..."). Thin —
// import + render, ChatScreen owns all behavior as the client island.
export const metadata: Metadata = { title: 'Chat — AdvisorDesk' };

export default function Page() {
  return (
    <PageContainer>
      <ChatScreen />
    </PageContainer>
  );
}
