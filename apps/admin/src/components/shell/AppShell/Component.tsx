'use client';

import { useRouter } from 'next/navigation';

import { AgentPanel } from '@/components/agent/AgentPanel';
import {
  AppBar,
  Box,
  Button,
  Drawer,
  Icon,
  IconButton,
  Link,
  NavList,
  ToolbarSpacer,
} from '@/components/common';
import { useGetMeQuery, useLogoutMutation } from '@/lib/api/authApi';
import { AGENT_BUTTON_LABEL, APP_NAME, MAIN_NAV_LABEL, OPEN_NAVIGATION_LABEL } from '@/lib/copy';

import { AccountMenu } from './components/AccountMenu';
import type { AppShellProps } from './interface';
import { useAppShell } from './useAppShell';

// task-04: the authenticated frame (AppBar + Drawer nav + user menu) tasks
// 05/06 and the phase-5 panel toggle mount into via the children slot.
// phase-8 task-15 (DESIGN.md §C1): layout state (`isNarrow`/`navOpen`/`agentOpen`/`navItems`)
// moved into the colocated `useAppShell` hook; the account menu extracted into its own leaf
// (`components/AccountMenu`) — `AppShell` itself is now just the frame + the two data hooks
// (`useGetMeQuery`/`useLogoutMutation`) and `useRouter`, per the brief's Interfaces section.
export default function Component({ children }: AppShellProps) {
  const router = useRouter();
  const { data: me } = useGetMeQuery();
  const [logout] = useLogoutMutation();
  const shell = useAppShell();

  const handleSignOut = () => {
    void logout().finally(() => {
      router.push('/signin');
    });
  };

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <AppBar>
        {shell.isNarrow ? (
          <IconButton
            name="Menu"
            label={OPEN_NAVIGATION_LABEL}
            onClick={shell.openNav}
            color="inherit"
            edge="start"
          />
        ) : null}
        <Link
          href="/"
          variant="h6"
          underline="none"
          color="inherit"
          sx={{ mr: 3, whiteSpace: 'nowrap' }}
        >
          {APP_NAME}
        </Link>
        <Box sx={{ flexGrow: 1 }} />
        {/* User checkpoint (phase-5): both AppBar buttons rendered theme-primary text on the
            primary-colored bar — present in the a11y tree, invisible to the eye. `inherit`
            picks up the AppBar's contrast text color (the standard MUI AppBar idiom). */}
        <Button
          variant="outlined"
          color="inherit"
          startIcon={<Icon name="SmartToy" />}
          aria-haspopup="true"
          aria-expanded={shell.agentOpen}
          aria-controls="app-shell-agent-panel"
          onClick={shell.toggleAgent}
        >
          {AGENT_BUTTON_LABEL}
        </Button>
        {me ? (
          <AccountMenu
            name={me.name ?? me.email}
            avatarUrl={me.avatar_url}
            onSignOut={handleSignOut}
          />
        ) : null}
      </AppBar>
      <Drawer
        variant={shell.isNarrow ? 'temporary' : 'permanent'}
        open={shell.isNarrow ? shell.navOpen : true}
        onClose={shell.closeNav}
      >
        <Box component="nav" aria-label={MAIN_NAV_LABEL}>
          <NavList items={shell.navItems} onNavigate={shell.closeNav} />
        </Box>
      </Drawer>
      <Box component="main" sx={{ flexGrow: 1, minWidth: 0, p: { xs: 2, md: 3 } }}>
        <ToolbarSpacer />
        {children}
      </Box>
      {/* phase-8 task-15: `onClose` REMOVED — a persistent drawer never fires it (the phase-6
          "dead Drawer onClose" backlog item). The panel's own close button (task-23) and the
          AppBar toggle above are the only close paths, both driving `agentOpen`/`closeAgent`. */}
      <Drawer
        id="app-shell-agent-panel"
        anchor="right"
        variant="persistent"
        open={shell.agentOpen}
        width={shell.isNarrow ? '100vw' : 400}
      >
        <AgentPanel onClose={shell.closeAgent} />
      </Drawer>
    </Box>
  );
}
