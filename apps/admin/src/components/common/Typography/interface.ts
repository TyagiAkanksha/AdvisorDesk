import type { TypographyProps as MuiTypographyProps } from '@mui/material/Typography';

// Thin pass-through of MUI's own prop type (docs/FRONTEND-CONVENTIONS.md §4) — Typography is a
// generic text primitive (variant + polymorphic `component`), not a bespoke contract like Icon.
// Twin copy: apps/client/src/components/common/Typography/interface.ts (task-04 — the two apps
// deploy independently, so this primitive is duplicated rather than shared, same as theme.ts).
export type TypographyProps = MuiTypographyProps;
