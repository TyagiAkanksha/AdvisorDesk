'use client';

import MuiButton from '@mui/material/Button';
import Link from 'next/link';

import type { ButtonProps } from './interface';

// phase-8 task-06: an INTERNAL `href` (starts with `/`) renders via `next/link`'s `Link` —
// client-side navigation, no full page reload — same pattern as apps/admin/src/components/
// common/Button/Component.tsx and this app's own common/Link/Component.tsx. An EXTERNAL `href`
// is untouched: MUI's own `href`-without-`component` behavior still renders a plain `<a>`.
// Either way the rendered element is an `<a>` with the same accessible `link` role, name, and
// `href` attribute. Marked 'use client': next/link is a function value passed as `component` —
// the same RSC-boundary reason as common/Link/Component.tsx's header comment.
function isInternalHref(href: string): boolean {
  return href.startsWith('/');
}

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
