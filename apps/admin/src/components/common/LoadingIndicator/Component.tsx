import MuiCircularProgress from '@mui/material/CircularProgress';

import { Box } from '../Box';

// Zero-prop — no interface.ts per docs/FRONTEND-CONVENTIONS.md §3. `CircularProgress`'s
// default role is `progressbar` — the visible, non-silent loading state §9 requires.
export default function Component() {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
      <MuiCircularProgress aria-label="Loading" />
    </Box>
  );
}
