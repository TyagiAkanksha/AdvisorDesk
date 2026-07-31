import MuiLink from '@mui/material/Link';
import NextLink from 'next/link';

import type { LinkProps } from './interface';

// Mirrors apps/admin/src/components/common/Button/Component.tsx's `isInternalHref` split.
function isInternalHref(href: string): boolean {
  return href.startsWith('/');
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
