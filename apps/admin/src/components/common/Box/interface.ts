import type { BoxProps as MuiBoxProps } from '@mui/material/Box';

// Thin pass-through of MUI's own prop type (docs/FRONTEND-CONVENTIONS.md §4) —
// Box is a generic layout primitive (flex/grid scaffolding, `sx`), not a
// bespoke contract like Icon.
export type BoxProps = MuiBoxProps;
