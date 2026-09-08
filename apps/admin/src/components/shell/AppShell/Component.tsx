'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { AgentPanel } from '@/components/agent/AgentPanel';
import {
  AppBar,
  Avatar,
  Box,
  Button,
  Drawer,
  Menu,
  NavList,
  ToolbarSpacer,
} from '@/components/common';
import { useGetMeQuery, useLogoutMutation } from '@/lib/api/authApi';

import type { AppShellProps } from './interface';

// task-04: the authenticated frame (AppBar + Drawer nav + user menu) tasks
// 05/06 and the phase-5 panel toggle mount into via the children slot.
const NAV_ITEMS = [
  { label: 'Dashboard', href: '/' },
  { label: 'Content', href: '/content' },
  // mcp-oauth task-09: the admin "Connected apps" page (docs/plans/mcp-oauth/task-09-admin-connected-apps-ui.md).
  { label: 'Connected apps', href: '/connected-apps' },
];

export default function Component({ children }: AppShellProps) {
  const router = useRouter();
  const { data: me } = useGetMeQuery();
  const [logout] = useLogoutMutation();
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  // phase-5 task-04: the agent panel's open/closed VISUAL state lives here, ABOVE the
  // `children` route outlet — `AgentPanel` itself is always mounted (never conditionally
  // rendered) so its own `useAgentStream` conversation state survives navigation between pages
  // (brief's Interfaces section); only the wrapping Drawer's `open` toggles.
  const [agentPanelOpen, setAgentPanelOpen] = useState(false);

  const handleSignOut = () => {
    void logout().finally(() => {
      router.push('/signin');
    });
  };

  const userName = me?.name ?? me?.email ?? '';
  const accountMenuOpen = Boolean(anchorEl);

  return (
    <Box sx={{ display: 'flex' }}>
      <AppBar>
        <Box sx={{ flexGrow: 1 }} />
        {/* User checkpoint (phase-5): both AppBar buttons rendered theme-primary text on the
            primary-colored bar — present in the a11y tree, invisible to the eye. `inherit`
            picks up the AppBar's contrast text color (the standard MUI AppBar idiom). */}
        <Button
          color="inherit"
          aria-haspopup="true"
          aria-expanded={agentPanelOpen}
          aria-controls="app-shell-agent-panel"
          onClick={() => setAgentPanelOpen((prev) => !prev)}
        >
          Agent
        </Button>
        {me ? (
          <Button
            color="inherit"
            aria-haspopup="true"
            aria-expanded={accountMenuOpen}
            // Fix round 1 (review finding #2, Minor): unlike the agent panel's `Drawer`
            // (`variant="persistent"`, always in the DOM), this `Menu` is a MUI `Popover`/`Modal`
            // that fully unmounts while closed — a static `aria-controls` here would dangle,
            // pointing at an id that doesn't exist most of the time. Only advertise it while the
            // target actually resolves, mirroring `aria-expanded`'s own open/closed split.
            aria-controls={accountMenuOpen ? 'app-shell-account-menu' : undefined}
            onClick={(event) => setAnchorEl(event.currentTarget)}
          >
            {/* WR-66: decorative — the visible `userName` text right after it already carries
                the accessible name, so the avatar itself is hidden from the a11y tree to avoid
                announcing the name twice. */}
            <Avatar alt="" aria-hidden src={me.avatar_url}>
              {userName.charAt(0)}
            </Avatar>
            {userName}
          </Button>
        ) : null}
        <Menu
          id="app-shell-account-menu"
          anchorEl={anchorEl}
          open={accountMenuOpen}
          onClose={() => setAnchorEl(null)}
          options={[{ label: 'Sign out', onSelect: handleSignOut }]}
        />
      </AppBar>
      <Drawer>
        <NavList items={NAV_ITEMS} />
      </Drawer>
      <Box component="main" sx={{ flexGrow: 1, p: 3 }}>
        <ToolbarSpacer />
        {children}
      </Box>
      <Drawer
        id="app-shell-agent-panel"
        anchor="right"
        variant="persistent"
        open={agentPanelOpen}
        onClose={() => setAgentPanelOpen(false)}
      >
        <AgentPanel />
      </Drawer>
    </Box>
  );
}
