import type { ChipProps as MuiChipProps } from '@mui/material/Chip';
import type { ElementType } from 'react';

// Thin pass-through of MUI's own prop type (docs/FRONTEND-CONVENTIONS.md §4). phase-8 task-14
// (apps/admin) — mirrors apps/client's generic Chip: admin's tags/status semantics have their
// own bespoke primitive (`StatusChip`), so this stays a plain pass-through for anything else
// that needs a chip (e.g. a client id, a tag).
//
// Kept GENERIC — mirroring MUI's own `ChipProps<RootComponent>` signature — rather than frozen
// to the `component="div"` default, so a caller can render Chip as a real anchor (`<Chip<'a'>
// component="a" href="..." clickable />`) and get `href`/`title` typed for free via MUI's own
// `OverrideProps` merge. Verified empirically (apps/client task-05) that this renders a real
// `<a href>` (native `role="link"`, not `role="button"` via `ButtonBase`) and type-checks
// cleanly with an explicit JSX type argument at the call site (`<Chip<'a'> ...>`) — a plain
// non-generic prop-type union does NOT type-check here (TS can't resolve `MuiChip`'s
// overloaded/polymorphic signature from a spread union).
export type ChipProps<RootComponent extends ElementType = 'div'> = MuiChipProps<RootComponent>;
