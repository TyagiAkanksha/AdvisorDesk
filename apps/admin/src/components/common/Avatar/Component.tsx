import MuiAvatar from '@mui/material/Avatar';

import type { AvatarProps } from './interface';

export default function Component({ alt, src, children, 'aria-hidden': ariaHidden }: AvatarProps) {
  return (
    <MuiAvatar alt={alt} src={src ?? undefined} aria-hidden={ariaHidden}>
      {children}
    </MuiAvatar>
  );
}
