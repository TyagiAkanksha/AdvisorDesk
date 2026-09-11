'use client';

import { usePathname } from 'next/navigation';

import { Box, Link } from '@/components/common';
import { NAV_ARTICLES_LABEL, NAV_ASK_LABEL } from '@/lib/copy';

// phase-8 task-08 (DESIGN.md §B1). The one piece of the shell that needs the browser: the
// active link comes from `usePathname`. Kept as its own leaf so `SiteHeader` stays a Server
// Component (docs/FRONTEND-CONVENTIONS.md §6 — push 'use client' down to the smallest leaf).
const NAV_ITEMS = [
  { label: NAV_ARTICLES_LABEL, href: '/' },
  { label: NAV_ASK_LABEL, href: '/chat' },
] as const;

function isActive(pathname: string, href: string): boolean {
  return href === '/'
    ? pathname === '/' || pathname.startsWith('/content')
    : pathname.startsWith(href);
}

export default function Component() {
  const pathname = usePathname();

  return (
    <Box component="nav" aria-label="Primary" sx={{ display: 'flex', gap: 3 }}>
      {NAV_ITEMS.map((item) => {
        const active = isActive(pathname, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? 'page' : undefined}
            underline="none"
            sx={{
              fontWeight: active ? 600 : 500,
              color: active ? 'primary.main' : 'text.secondary',
            }}
          >
            {item.label}
          </Link>
        );
      })}
    </Box>
  );
}
