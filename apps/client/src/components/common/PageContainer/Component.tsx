import Container from '@mui/material/Container';

import type { PageContainerProps } from './interface';

export default function Component({ children, maxWidth }: PageContainerProps) {
  return (
    <Container component="main" maxWidth={maxWidth ?? 'lg'} sx={{ py: 4 }}>
      {children}
    </Container>
  );
}
