'use client';

import MuiButton from '@mui/material/Button';
import Link from 'next/link';

import { isInternalHref } from '@/lib/href';

import type { ButtonProps } from './interface';

// The internal/external split is `isInternalHref` (src/lib/href.ts, hygiene t02). Marked 'use
// client': next/link is a function value passed as `component` — the same RSC-boundary reason as
// common/Link/Component.tsx's header comment.
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
