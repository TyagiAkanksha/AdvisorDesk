import type { ReactNode } from 'react';

import { RequireSession } from '@/components/auth/RequireSession';
import { AppShell } from '@/components/shell/AppShell';

// task-04: this route group owns every authenticated admin page — nested under RootLayout's
// Providers. hygiene t05 (p8 final X4): the shell now wraps the session gate, not the other
// way round — the AppBar/drawer paint immediately, and the session spinner and the error state
// render inside <main>, and the 401 redirect fires with the shell already up.
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <AppShell>
      <RequireSession>{children}</RequireSession>
    </AppShell>
  );
}
