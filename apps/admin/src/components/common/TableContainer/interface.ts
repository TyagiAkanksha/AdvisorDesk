import type { TableContainerProps as MuiTableContainerProps } from '@mui/material/TableContainer';
import type { ElementType } from 'react';

// Thin pass-through of MUI's own prop type (docs/FRONTEND-CONVENTIONS.md §4) — a generic
// primitive like Box, not a bespoke contract like Icon. phase-8 task-04.
// phase-8 task-18: made GENERIC (same precedent as `common/Chip`) so a caller can render
// TableContainer polymorphically (`<TableContainer<typeof Paper> component={Paper}
// variant="outlined">`) with the root component's own props (e.g. Paper's `variant`) typed in
// via MUI's `OverrideProps` merge — the previous non-generic alias only ever resolved against
// the default `'div'` root, so `variant` wasn't recognized when passing `component={Paper}`.
export type TableContainerProps<RootComponent extends ElementType = 'div'> =
  MuiTableContainerProps<RootComponent>;
