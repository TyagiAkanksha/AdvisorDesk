import MuiCard from '@mui/material/Card';
import MuiCardContent from '@mui/material/CardContent';

import type { CardProps } from './interface';

// Always pairs `Card` with `CardContent` — no call site has needed a bare `Card` without its
// content padding yet (docs/FRONTEND-CONVENTIONS.md §4: "grow common/ on demand").
export default function Component({ children, ...rest }: CardProps) {
  return (
    <MuiCard {...rest}>
      <MuiCardContent>{children}</MuiCardContent>
    </MuiCard>
  );
}
