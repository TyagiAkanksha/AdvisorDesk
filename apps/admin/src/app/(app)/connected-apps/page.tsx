import type { Metadata } from 'next';

import { PageContainer } from '@/components/common';
import { ConnectedAppsScreen } from '@/components/connectedApps/ConnectedAppsScreen';

export const metadata: Metadata = { title: 'Connected apps' };

export default function Page() {
  return (
    <PageContainer>
      <ConnectedAppsScreen />
    </PageContainer>
  );
}
