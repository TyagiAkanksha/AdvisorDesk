import MuiLink from '@mui/material/Link';
import NextLink from 'next/link';

import type { LinkProps } from './interface';

// Twin copy: apps/client/src/components/common/Link/Component.tsx (task-04). Same
// `isInternalHref` split as this app's own common/Button/Component.tsx.
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
