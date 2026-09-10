import MuiToolbar from '@mui/material/Toolbar';

import type { ToolbarProps } from './interface';

export default function Component(props: ToolbarProps) {
  return <MuiToolbar {...props} />;
}
