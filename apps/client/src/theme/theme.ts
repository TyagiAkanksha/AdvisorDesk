// AdvisorDesk shared design tokens (docs/FRONTEND-CONVENTIONS.md §2).
//
// This file is INTENTIONALLY duplicated — its twin copy is
// apps/admin/src/theme/theme.ts. The two Next.js apps deploy independently, so each
// carries its own `createTheme()` rather than importing a shared package; keep the
// token VALUES identical between the two copies when either one changes.
import { createTheme } from '@mui/material/styles';

export const theme = createTheme({
  palette: {
    primary: {
      // Deep navy — trust/stability register for an advisory product.
      main: '#1E3A5F',
    },
    secondary: {
      // Muted gold accent, used sparingly for calls to action.
      main: '#C08A28',
    },
  },
  typography: {
    fontFamily: [
      '-apple-system',
      'BlinkMacSystemFont',
      '"Segoe UI"',
      'Roboto',
      '"Helvetica Neue"',
      'Arial',
      'sans-serif',
    ].join(','),
  },
  shape: {
    borderRadius: 8,
  },
  // spacing is intentionally left at the MUI default (theme.spacing(n) = n * 8px).
});
