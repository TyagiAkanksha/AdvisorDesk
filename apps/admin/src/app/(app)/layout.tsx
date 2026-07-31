import type { ReactNode } from 'react';

import { RequireSession } from '@/components/auth/RequireSession';
import { AppShell } from '@/components/shell/AppShell';

// task-04: this route group owns every authenticated admin page — nested
// under RootLayout's Providers, gated by RequireSession, framed by AppShell.
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <RequireSession>
      <AppShell>{children}</AppShell>
    </RequireSession>
  );
}
