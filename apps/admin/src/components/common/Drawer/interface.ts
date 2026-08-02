import type { ReactNode } from 'react';

/**
 * A themed MUI Drawer. Defaults (`anchor="left"`, `variant="permanent"`) reproduce the admin
 * shell's original zero-prop nav drawer unchanged; phase-5 task-04 adds the `anchor="right"`,
 * `variant="persistent"` shape the agent panel needs (toggled open/closed from outside, stays
 * mounted either way) rather than a second near-duplicate wrapped-Drawer component in
 * `common/` (docs/FRONTEND-CONVENTIONS.md §4: "grow common/ on demand").
 */
export interface DrawerProps {
  children: ReactNode;
  anchor?: 'left' | 'right';
  variant?: 'permanent' | 'persistent';
  /** Ignored by `variant="permanent"` (MUI: always open). Required to actually toggle a
   * `variant="persistent"` drawer. */
  open?: boolean;
  onClose?: () => void;
}
