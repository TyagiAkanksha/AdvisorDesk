import type { CardProps as MuiCardProps } from '@mui/material/Card';

// Thin pass-through of MUI's own `Card` prop type (docs/FRONTEND-CONVENTIONS.md §4) — this
// wrapper hides the `Card`/`CardContent` pairing (see Component.tsx) behind one call site, the
// same way `PageContainer` hides its `Container` config.
export type CardProps = MuiCardProps;
