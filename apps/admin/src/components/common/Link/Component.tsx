'use client';

import MuiLink from '@mui/material/Link';
import NextLink from 'next/link';

import { isInternalHref } from '@/lib/href';

import type { LinkProps } from './interface';

// task-04 fix round 1 (F1): isolated client leaf — identical latent defect to the client app's
// twin (`component={NextLink}`, a function, isn't serializable across an RSC boundary into
// MUI's own `'use client'` Link), currently masked here only because every current call site
// (ContentListScreen, ContentEditorScreen) is already inside a `'use client'` island; a future
// server-component call site would 500 exactly like apps/client's did. Twin copy: apps/client/
// src/components/common/Link/Component.tsx (task-04).
// The internal/external split is `isInternalHref` (src/lib/href.ts, hygiene t02).
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
