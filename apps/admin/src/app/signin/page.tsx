import type { Metadata } from 'next';

import { SignInScreen } from '@/components/auth/SignInScreen';
import { PageContainer } from '@/components/common';

export const metadata: Metadata = { title: 'Sign in' };

export default function Page() {
  return (
    <PageContainer>
      <SignInScreen />
    </PageContainer>
  );
}
