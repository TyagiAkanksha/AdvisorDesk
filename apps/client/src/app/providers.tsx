'use client';

import { AppRouterCacheProvider } from '@mui/material-nextjs/v16-appRouter';
import CssBaseline from '@mui/material/CssBaseline';
import { ThemeProvider } from '@mui/material/styles';
import type { ReactNode } from 'react';

import { theme } from '@/theme/theme';

// Client-component boundary for MUI's App Router SSR wiring (docs/FRONTEND-CONVENTIONS.md §2):
// AppRouterCacheProvider (Emotion insertion-point cache) -> ThemeProvider(theme) -> CssBaseline.
// Split out from layout.tsx so theme.ts stays importable from Server Components too.
export default function Providers({ children }: { children: ReactNode }) {
  return (
    <AppRouterCacheProvider>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </AppRouterCacheProvider>
  );
}
