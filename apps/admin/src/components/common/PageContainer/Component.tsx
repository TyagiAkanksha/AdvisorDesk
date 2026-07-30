import Container from '@mui/material/Container';
import type { PropsWithChildren } from 'react';

// Zero custom props (just `children`) — no interface.ts per
// docs/FRONTEND-CONVENTIONS.md §3 ("zero-prop components have no interface.ts");
// `PropsWithChildren` is React's own type, not one authored here.
export default function Component({ children }: PropsWithChildren) {
  return (
    <Container component="main" maxWidth="lg" sx={{ py: 4 }}>
      {children}
    </Container>
  );
}
