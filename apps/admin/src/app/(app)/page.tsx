import type { Metadata } from 'next';

import { PageContainer } from '@/components/common';
import { DashboardScreen } from '@/components/dashboard/DashboardScreen';

// task-05: the phase-1 placeholder becomes the real dashboard page.
export const metadata: Metadata = { title: 'Dashboard' };

export default function Page() {
  return (
    <PageContainer>
      <DashboardScreen />
    </PageContainer>
  );
}
