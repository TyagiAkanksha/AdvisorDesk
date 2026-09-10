import type { CircularProgressProps as MuiCircularProgressProps } from '@mui/material/CircularProgress';

// Thin pass-through of MUI's own prop type (docs/FRONTEND-CONVENTIONS.md §4) — a generic layout
// primitive like Box, not a bespoke contract like Icon. phase-8 task-12: the chat screen's
// Thinking… indicator needs a real progress affordance (`role="progressbar"`), not an icon.
export type CircularProgressProps = MuiCircularProgressProps;
