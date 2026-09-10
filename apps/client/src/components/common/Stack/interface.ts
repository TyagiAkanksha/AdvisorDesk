import type { StackProps as MuiStackProps } from '@mui/material/Stack';

// Thin pass-through of MUI's own prop type (docs/FRONTEND-CONVENTIONS.md §4) — a generic layout
// primitive like Box, not a bespoke contract like Icon. phase-8 task-06.
export type StackProps = MuiStackProps;
