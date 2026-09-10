import MuiTable from '@mui/material/Table';

import type { TableProps } from './interface';

export default function Component(props: TableProps) {
  return <MuiTable {...props} />;
}
