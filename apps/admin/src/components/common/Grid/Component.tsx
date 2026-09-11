import MuiGrid from '@mui/material/Grid';

import type { GridProps } from './interface';

export default function Component(props: GridProps) {
  return <MuiGrid {...props} />;
}
