import type { GridProps as MuiGridProps } from '@mui/material/Grid';

// Thin pass-through of MUI's own prop type (docs/FRONTEND-CONVENTIONS.md §4) — a generic layout
// primitive like Box, not a bespoke contract like Icon. phase-8 task-14 (apps/admin). MUI 9's
// Grid merges the old `item`/`container` split into one component: `<Grid container><Grid
// size={{ xs: 12, sm: 6, md: 4 }}>...</Grid></Grid>`.
export type GridProps = MuiGridProps;
