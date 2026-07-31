import type { TypographyProps as MuiTypographyProps } from '@mui/material/Typography';

// Thin pass-through of MUI's own prop type (docs/FRONTEND-CONVENTIONS.md §4) — Typography is a
// generic text primitive (variant + polymorphic `component`), not a bespoke contract like Icon.
export type TypographyProps = MuiTypographyProps;
