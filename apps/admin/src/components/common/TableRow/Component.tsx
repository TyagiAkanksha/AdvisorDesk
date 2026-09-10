import MuiTableRow from '@mui/material/TableRow';

import type { TableRowProps } from './interface';

export default function Component(props: TableRowProps) {
  return <MuiTableRow {...props} />;
}
