'use client';

import MuiButton from '@mui/material/Button';
import Link from 'next/link';

import type { ButtonProps } from './interface';

// fix round 2, N4b: an INTERNAL `href` (starts with `/`, e.g. ContentListScreen's "New content"
// link) now renders via `next/link`'s `Link` — client-side navigation, no full page reload —
// the same `component={Link}` pattern common/NavList already uses. An EXTERNAL `href` (e.g.
// SignInScreen's OAuth redirect — task-04 pinned: "a REAL anchor navigation... never a
// JS-driven fetch") is untouched: MUI's own `href`-without-`component` behavior still renders a
// plain `<a>`, so the browser still does a real navigation for those. Either way the rendered
// element is an `<a>` with the same accessible `link` role, name, and `href` attribute.
// phase-8 task-07: `'use client'` added — this file had the identical latent defect its sibling
// `common/Link/Component.tsx` (task-04 fix round 1, F1) already documents and fixes: passing
// `Link` (a function) as `component` isn't serializable across an RSC boundary into MUI's own
// `'use client'` Button, and every call site here used to be inside a `'use client'` island. The
// new root `app/not-found.tsx` (task-07) is a Server Component that renders this `Button` with
// an internal `href` — exactly the "future server-component call site" the Link comment
// predicted — and `next build` 500s on it without this directive.
// p8 final: `//` guard added to match `common/Link`'s `isInternalHref` — a protocol-relative
// `//host` URL starts with `/` but must render as a plain external anchor, not route through
// next/link.
function isInternalHref(href: string): boolean {
  return href.startsWith('/') && !href.startsWith('//');
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
