import MuiTooltip from '@mui/material/Tooltip';

import type { TooltipProps } from './interface';

export default function Component(props: TooltipProps) {
  return <MuiTooltip {...props} />;
}
