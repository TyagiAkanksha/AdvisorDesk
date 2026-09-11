'use client';

import { useState } from 'react';

import { Avatar, Button, Menu } from '@/components/common';
import { SIGN_OUT_LABEL } from '@/lib/copy';

import type { AccountMenuProps } from './interface';

// phase-8 task-15 (DESIGN.md §C1): extracted verbatim out of AppShell/Component.tsx — the anchor
// element is the ONLY piece of state this leaf owns (presentational, not shell layout state).
export default function Component({ name, avatarUrl, onSignOut }: AccountMenuProps) {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const open = Boolean(anchorEl);

  return (
    <>
      <Button
        color="inherit"
        aria-haspopup="true"
        aria-expanded={open}
        // Fix round 1 (review finding #2, Minor): unlike the agent panel's `Drawer`
        // (`variant="persistent"`, always in the DOM), this `Menu` is a MUI `Popover`/`Modal`
        // that fully unmounts while closed — a static `aria-controls` here would dangle,
        // pointing at an id that doesn't exist most of the time. Only advertise it while the
        // target actually resolves, mirroring `aria-expanded`'s own open/closed split.
        aria-controls={open ? 'app-shell-account-menu' : undefined}
        onClick={(event) => setAnchorEl(event.currentTarget)}
      >
        {/* WR-66: decorative — the visible `name` text right after it already carries the
            accessible name, so the avatar itself is hidden from the a11y tree to avoid
            announcing the name twice. */}
        <Avatar alt="" aria-hidden src={avatarUrl}>
          {name.charAt(0)}
        </Avatar>
        {name}
      </Button>
      <Menu
        id="app-shell-account-menu"
        anchorEl={anchorEl}
        open={open}
        onClose={() => setAnchorEl(null)}
        options={[{ label: SIGN_OUT_LABEL, onSelect: onSignOut }]}
      />
    </>
  );
}
