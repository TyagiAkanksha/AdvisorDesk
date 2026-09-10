import MuiAlert from '@mui/material/Alert';

import type { AlertProps } from './interface';

export default function Component(props: AlertProps) {
  return <MuiAlert {...props} />;
}
