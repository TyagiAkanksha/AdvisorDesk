import type { ChipProps as MuiChipProps } from '@mui/material/Chip';
import type { ElementType } from 'react';

// Thin pass-through of MUI's own prop type (docs/FRONTEND-CONVENTIONS.md §4). Unlike
// apps/admin's `StatusChip` (a bespoke content-status → color lookup), client-side tags are
// plain strings with no status semantics, so a generic Chip primitive is the right shape here.
//
// task-05 review round 1, M-2: kept GENERIC — mirroring MUI's own `ChipProps<RootComponent>`
// signature — rather than frozen to the `component="div"` default, so a caller can render Chip
// as a real anchor (`<Chip<'a'> component="a" href="..." clickable />`) and get `href`/`title`
// typed for free via MUI's own `OverrideProps` merge (`CitationList` — a citation "chip" that
// links to `/content/{slug}`). MUI's own `Chip` docstring: "[clickable] can be used, for
// example, along with the component prop to indicate an anchor Chip is clickable." Verified
// empirically that this renders a real `<a href>` (native `role="link"`, not `role="button"`
// via `ButtonBase`) and type-checks cleanly with an explicit JSX type argument at the call site
// (`<Chip<'a'> ...>`) — a plain non-generic prop-type union does NOT type-check here (TS can't
// resolve `MuiChip`'s overloaded/polymorphic signature from a spread union).
export type ChipProps<RootComponent extends ElementType = 'div'> = MuiChipProps<RootComponent>;
