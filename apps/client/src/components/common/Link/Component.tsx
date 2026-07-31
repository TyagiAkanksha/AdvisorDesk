'use client';

import MuiLink from '@mui/material/Link';
import NextLink from 'next/link';

import type { LinkProps } from './interface';

// task-04 fix round 1 (F1): isolated client leaf. `component={NextLink}` passes a function
// value into MUI's own `'use client'` Link — a Server Component can't hand a function across
// the RSC boundary (not serializable), so every internal-href render crashed the page with a
// 500 (jsdom has no RSC boundary and `next build` never renders dynamic routes, which is why
// the pinned component tests and a green build both missed this — only a running `next start`
// request surfaces it). Mirrors the standard MUI App Router pattern: push `'use client'` down
// to the smallest leaf that needs it, not up to the whole tree. Twin copy: apps/admin/src/
// components/common/Link/Component.tsx.
//
// Mirrors apps/admin/src/components/common/Button/Component.tsx's `isInternalHref` split.
function isInternalHref(href: string): boolean {
  return href.startsWith('/') && !href.startsWith('//');
}

export default function Component({ href, children, ...rest }: LinkProps) {
  if (isInternalHref(href)) {
    return (
      <MuiLink component={NextLink} href={href} {...rest}>
        {children}
      </MuiLink>
    );
  }
  return (
    <MuiLink href={href} {...rest}>
      {children}
    </MuiLink>
  );
}
