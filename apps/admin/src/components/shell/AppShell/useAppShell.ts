'use client';

import { usePathname } from 'next/navigation';
import { useState } from 'react';

import type { NavListItem } from '@/components/common';
import { useBreakpointDown } from '@/components/common';
import { CONNECTED_APPS_TITLE, CONTENT_TITLE, DASHBOARD_TITLE } from '@/lib/copy';
import { isActivePath } from '@/lib/navigation';

// phase-8 task-15 (DESIGN.md §C1): the three admin routes, in nav order. Colocated with the
// hook that turns them into `NavListItem[]` — not exported, `useAppShell`'s `navItems` result
// is the only public surface a caller needs.
const NAV_ITEMS: Array<{ label: string; href: string; icon: NonNullable<NavListItem['icon']> }> = [
  { label: DASHBOARD_TITLE, href: '/', icon: 'Dashboard' },
  { label: CONTENT_TITLE, href: '/content', icon: 'Article' },
  { label: CONNECTED_APPS_TITLE, href: '/connected-apps', icon: 'Link' },
];

export interface UseAppShellResult {
  /** Below the `md` breakpoint (`useBreakpointDown('md')`). */
  isNarrow: boolean;
  /** Temporary nav drawer state — only meaningful while `isNarrow`. */
  navOpen: boolean;
  openNav: () => void;
  closeNav: () => void;
  agentOpen: boolean;
  toggleAgent: () => void;
  closeAgent: () => void;
  /** The three routes with icons and `selected` computed from `usePathname()`. */
  navItems: NavListItem[];
}

export function useAppShell(): UseAppShellResult {
  const pathname = usePathname();
  const isNarrow = useBreakpointDown('md');
  const [navOpen, setNavOpen] = useState(false);
  // phase-5 task-04: the agent panel's open/closed VISUAL state lives here, ABOVE the
  // `children` route outlet — `AgentPanel` itself is always mounted (never conditionally
  // rendered) so its own `useAgentStream` conversation state survives navigation between pages;
  // only the wrapping Drawer's `open` toggles.
  const [agentOpen, setAgentOpen] = useState(false);

  const navItems: NavListItem[] = NAV_ITEMS.map((item) => ({
    ...item,
    selected: isActivePath(pathname, item.href),
  }));

  return {
    isNarrow,
    navOpen,
    openNav: () => setNavOpen(true),
    closeNav: () => setNavOpen(false),
    agentOpen,
    toggleAgent: () => setAgentOpen((prev) => !prev),
    closeAgent: () => setAgentOpen(false),
    navItems,
  };
}
