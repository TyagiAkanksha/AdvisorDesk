'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

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
];

export default function Component({ children }: AppShellProps) {
  const router = useRouter();
  const { data: me } = useGetMeQuery();
  const [logout] = useLogoutMutation();
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);

  const handleSignOut = () => {
    void logout().finally(() => {
      router.push('/signin');
    });
  };

  const userName = me?.name ?? me?.email ?? '';

  return (
    <Box sx={{ display: 'flex' }}>
      <AppBar>
        <Box sx={{ flexGrow: 1 }} />
        {me ? (
          <Button onClick={(event) => setAnchorEl(event.currentTarget)}>
            <Avatar alt={userName} src={me.avatar_url}>
              {userName.charAt(0)}
            </Avatar>
            {userName}
          </Button>
        ) : null}
        <Menu
          anchorEl={anchorEl}
          open={Boolean(anchorEl)}
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
    </Box>
  );
}
