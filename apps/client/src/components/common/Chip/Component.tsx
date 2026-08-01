import MuiChip from '@mui/material/Chip';
import type { ElementType } from 'react';

import type { ChipProps } from './interface';

export default function Component<RootComponent extends ElementType = 'div'>(
  props: ChipProps<RootComponent>,
) {
  return <MuiChip {...props} />;
}
