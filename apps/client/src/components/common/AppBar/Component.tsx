import MuiAppBar from '@mui/material/AppBar';

import type { AppBarProps } from './interface';

export default function Component(props: AppBarProps) {
  return <MuiAppBar {...props} />;
}
