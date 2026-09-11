import Container from '@mui/material/Container';
import type { PropsWithChildren } from 'react';

// Zero custom props (just `children`) — no interface.ts per
// docs/FRONTEND-CONVENTIONS.md §3 ("zero-prop components have no interface.ts");
// `PropsWithChildren` is React's own type, not one authored here.
// phase-8 task-15 (DESIGN.md §C1): no `component="main"`, no `py` — `AppShell` now renders the
// page's one `<main>` landmark and pads it once (`p: {xs: 2, md: 3}`); the root `not-found.tsx`
// (which renders outside AppShell) supplies its own `Box component="main"` wrapper instead.
export default function Component({ children }: PropsWithChildren) {
  return <Container maxWidth="lg">{children}</Container>;
}
