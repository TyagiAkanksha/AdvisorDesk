import MuiTableContainer from '@mui/material/TableContainer';
import type { ElementType } from 'react';

import type { TableContainerProps } from './interface';

export default function Component<RootComponent extends ElementType = 'div'>(
  props: TableContainerProps<RootComponent>,
) {
  return <MuiTableContainer {...props} />;
}
