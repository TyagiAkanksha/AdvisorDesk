import type { BoxProps as MuiBoxProps } from '@mui/material/Box';

// Thin pass-through of MUI's own prop type (docs/FRONTEND-CONVENTIONS.md §4) — Box is a generic
// layout primitive (flex/grid scaffolding, `sx`, polymorphic `component`), not a bespoke
// contract like Icon. Mirrors apps/admin/src/components/common/Box exactly. task-05 review
// round 1 (I-1/I-2/M-8): the chat screen's visual treatment (bubble alignment/color, the
// refusal's bordered/iconed panel, the empty-state block) needs an `sx`-capable container that
// a bare `<div>` can't provide.
export type BoxProps = MuiBoxProps;
