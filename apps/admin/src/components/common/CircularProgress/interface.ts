import type { CircularProgressProps as MuiCircularProgressProps } from '@mui/material/CircularProgress';

// Thin pass-through of MUI's own prop type (docs/FRONTEND-CONVENTIONS.md §4) — a generic layout
// primitive like Box, not a bespoke contract like Icon. phase-8 task-14 (apps/admin): the agent
// panel's "Working…" indicator needs a real progress affordance (`role="progressbar"`), not an
// icon.
export type CircularProgressProps = MuiCircularProgressProps;
