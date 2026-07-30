import MuiAppBar from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import type { PropsWithChildren } from 'react';

// Zero custom props (just `children`) — no interface.ts per
// docs/FRONTEND-CONVENTIONS.md §3. Bakes in the fixed AppBar+Toolbar pairing
// (every AppBar needs exactly one Toolbar) the same way PageContainer bakes
// in Container's fixed props.
export default function Component({ children }: PropsWithChildren) {
  return (
    <MuiAppBar position="fixed" color="primary">
      <Toolbar>{children}</Toolbar>
    </MuiAppBar>
  );
}
