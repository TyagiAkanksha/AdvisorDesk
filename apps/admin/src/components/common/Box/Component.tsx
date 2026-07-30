import MuiBox from '@mui/material/Box';

import type { BoxProps } from './interface';

export default function Component(props: BoxProps) {
  return <MuiBox {...props} />;
}
