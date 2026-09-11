import type { ReactNode } from 'react';

import { RequireSession } from '@/components/auth/RequireSession';
import { AppShell } from '@/components/shell/AppShell';

// task-04: this route group owns every authenticated admin page — nested under RootLayout's
// Providers. hygiene t05 (p8 final X4): the shell now wraps the session gate, not the other
// way round — the AppBar/drawer paint immediately and the session spinner / 401 redirect /
// error state render inside <main>, where the page will be, instead of on a blank page.
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <AppShell>
      <RequireSession>{children}</RequireSession>
    </AppShell>
  );
}
