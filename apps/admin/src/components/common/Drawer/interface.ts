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
  // 'temporary' added phase-8 task-04: the modal (overlay) variant the nav drawer switches to
  // below the md breakpoint (DESIGN.md §C1).
  variant?: 'permanent' | 'persistent' | 'temporary';
  /** Ignored by `variant="permanent"` (MUI: always open). Required to actually toggle a
   * `variant="persistent"` or `variant="temporary"` drawer. */
  open?: boolean;
  onClose?: () => void;
  // WR-13 (6R task-11): lets a toggle button's `aria-controls` reference this panel's DOM id.
  id?: string;
  /** Overrides the anchor's default width (240 left / 400 right), e.g. '100vw' on phones
   * (phase-8 task-04). */
  width?: number | string;
}
