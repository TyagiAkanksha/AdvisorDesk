import MuiDrawer from '@mui/material/Drawer';
import Toolbar from '@mui/material/Toolbar';

import type { DrawerProps } from './interface';

const NAV_DRAWER_WIDTH = 240;
const PANEL_DRAWER_WIDTH = 400;

// phase-2 t04's original nav drawer was zero-prop (permanent, fixed left, offset below the
// AppBar via the spacer Toolbar). phase-5 task-04 widens this to the one other drawer shape the
// app needs — a toggleable right panel — via optional props that default to the original
// behavior, rather than a second wrapped-Drawer component in `common/` (see interface.ts).
export default function Component({
  children,
  anchor = 'left',
  variant = 'permanent',
  open = true,
  onClose,
}: DrawerProps) {
  const width = anchor === 'left' ? NAV_DRAWER_WIDTH : PANEL_DRAWER_WIDTH;

  return (
    <MuiDrawer
      anchor={anchor}
      variant={variant}
      open={open}
      onClose={onClose}
      sx={{
        ...(variant === 'permanent' ? { width, flexShrink: 0 } : {}),
        '& .MuiDrawer-paper': { width, boxSizing: 'border-box' },
      }}
    >
      <Toolbar />
      {children}
    </MuiDrawer>
  );
}
