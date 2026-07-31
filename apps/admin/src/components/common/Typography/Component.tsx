import MuiTypography from '@mui/material/Typography';

import type { TypographyProps } from './interface';

// Twin copy: apps/client/src/components/common/Typography/Component.tsx (task-04).
export default function Component(props: TypographyProps) {
  return <MuiTypography {...props} />;
}
