'use client';

import { AppRouterCacheProvider } from '@mui/material-nextjs/v16-appRouter';
import CssBaseline from '@mui/material/CssBaseline';
import { ThemeProvider } from '@mui/material/styles';
import type { ReactNode } from 'react';
import { Provider as ReduxProvider } from 'react-redux';

import { SnackbarProvider } from '@/components/common';
import { store } from '@/lib/store';
import { theme } from '@/theme/theme';

// Client-component boundary for MUI's App Router SSR wiring (docs/FRONTEND-CONVENTIONS.md §2):
// AppRouterCacheProvider (Emotion insertion-point cache) -> ThemeProvider(theme) -> CssBaseline.
// Split out from layout.tsx so theme.ts stays importable from Server Components too.
// task-04: extended (not recreated) with the Redux store Provider — RTK Query's
// server cache + UI state (docs/FRONTEND-CONVENTIONS.md §6).
// task-05: extended with SnackbarProvider (inside Redux) — any screen can call
// `useSnackbar()` without owning its own AppSnackbar state.
export default function Providers({ children }: { children: ReactNode }) {
  return (
    <AppRouterCacheProvider>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <ReduxProvider store={store}>
          <SnackbarProvider>{children}</SnackbarProvider>
        </ReduxProvider>
      </ThemeProvider>
    </AppRouterCacheProvider>
  );
}
