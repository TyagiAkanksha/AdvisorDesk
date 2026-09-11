import MuiCircularProgress from '@mui/material/CircularProgress';

import type { CircularProgressProps } from './interface';

export default function Component(props: CircularProgressProps) {
  return <MuiCircularProgress {...props} />;
}
