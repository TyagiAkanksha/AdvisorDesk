import MuiAvatar from '@mui/material/Avatar';

import type { AvatarProps } from './interface';

export default function Component({ alt, src, children }: AvatarProps) {
  return (
    <MuiAvatar alt={alt} src={src ?? undefined}>
      {children}
    </MuiAvatar>
  );
}
