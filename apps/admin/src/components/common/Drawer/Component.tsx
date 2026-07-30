import MuiDrawer from '@mui/material/Drawer';
import Toolbar from '@mui/material/Toolbar';
import type { PropsWithChildren } from 'react';

const DRAWER_WIDTH = 240;

// Zero custom props (just `children`) — no interface.ts per
// docs/FRONTEND-CONVENTIONS.md §3. Fixed to the admin shell's one nav-drawer
// shape (permanent, fixed width, offset below the AppBar via the spacer
// Toolbar) rather than exposing MUI's full variant surface.
export default function Component({ children }: PropsWithChildren) {
  return (
    <MuiDrawer
      variant="permanent"
      sx={{
        width: DRAWER_WIDTH,
        flexShrink: 0,
        '& .MuiDrawer-paper': { width: DRAWER_WIDTH, boxSizing: 'border-box' },
      }}
    >
      <Toolbar />
      {children}
    </MuiDrawer>
  );
}
