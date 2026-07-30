import Toolbar from '@mui/material/Toolbar';

// Zero-prop — no interface.ts per docs/FRONTEND-CONVENTIONS.md §3. A bare
// (childless) `Toolbar` renders at the theme's toolbar height and nothing
// else; MUI's own "clipped drawer" pattern uses one as the first child of
// the main content area to push page content below a `position="fixed"`
// `AppBar`, which otherwise overlaps the top ~64px of every page (review
// round 1, I3). Kept as its own `common/` primitive (not inlined as a raw
// `<Toolbar />` at the call site) so `AppShell` and any future shell layout
// stay MUI-free per §4.
export default function Component() {
  return <Toolbar />;
}
