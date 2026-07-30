import MuiAppBar from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import type { PropsWithChildren } from 'react';

// Zero custom props (just `children`) — no interface.ts per
// docs/FRONTEND-CONVENTIONS.md §3. Bakes in the fixed AppBar+Toolbar pairing
// (every AppBar needs exactly one Toolbar) the same way PageContainer bakes
// in Container's fixed props.
//
// `zIndex: theme.zIndex.drawer + 1` (review round 1, I3): MUI's default
// z-index for a permanent `Drawer` (1200) is higher than a fixed `AppBar`
// (1100), so without this override the drawer paints over the app bar
// instead of sitting below it — the standard MUI "clipped drawer" pattern.
export default function Component({ children }: PropsWithChildren) {
  return (
    <MuiAppBar position="fixed" color="primary" sx={{ zIndex: (theme) => theme.zIndex.drawer + 1 }}>
      <Toolbar>{children}</Toolbar>
    </MuiAppBar>
  );
}
