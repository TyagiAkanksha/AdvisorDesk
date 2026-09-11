'use client';

import MuiButton from '@mui/material/Button';
import Link from 'next/link';

import { isInternalHref } from '@/lib/href';

import type { ButtonProps } from './interface';

// The internal/external split is `isInternalHref` (src/lib/href.ts, hygiene t02).
// phase-8 task-07: `'use client'` added — this file had the identical latent defect its sibling
// `common/Link/Component.tsx` (task-04 fix round 1, F1) already documents and fixes: passing
// `Link` (a function) as `component` isn't serializable across an RSC boundary into MUI's own
// `'use client'` Button, and every call site here used to be inside a `'use client'` island. The
// new root `app/not-found.tsx` (task-07) is a Server Component that renders this `Button` with
// an internal `href` — exactly the "future server-component call site" the Link comment
// predicted — and `next build` 500s on it without this directive.
export default function Component({ children, href, ...rest }: ButtonProps) {
  if (href && isInternalHref(href)) {
    return (
      <MuiButton component={Link} href={href} {...rest}>
        {children}
      </MuiButton>
    );
  }
  return (
    <MuiButton href={href} {...rest}>
      {children}
    </MuiButton>
  );
}
