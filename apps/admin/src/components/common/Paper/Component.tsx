import MuiPaper from '@mui/material/Paper';

import type { PaperProps } from './interface';

export default function Component(props: PaperProps) {
  return <MuiPaper {...props} />;
}
