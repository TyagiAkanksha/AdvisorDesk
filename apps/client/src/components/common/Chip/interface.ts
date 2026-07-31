import type { ChipProps as MuiChipProps } from '@mui/material/Chip';

// Thin pass-through of MUI's own prop type (docs/FRONTEND-CONVENTIONS.md §4). Unlike
// apps/admin's `StatusChip` (a bespoke content-status → color lookup), client-side tags are
// plain strings with no status semantics, so a generic Chip primitive is the right shape here.
export type ChipProps = MuiChipProps;
