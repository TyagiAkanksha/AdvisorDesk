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
