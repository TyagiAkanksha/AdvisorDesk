import MuiButton from '@mui/material/Button';

import type { ButtonProps } from './interface';

export default function Component({ children, ...rest }: ButtonProps) {
  return <MuiButton {...rest}>{children}</MuiButton>;
}
