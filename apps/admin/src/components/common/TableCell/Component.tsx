import MuiTableCell from '@mui/material/TableCell';

import type { TableCellProps } from './interface';

export default function Component(props: TableCellProps) {
  return <MuiTableCell {...props} />;
}
