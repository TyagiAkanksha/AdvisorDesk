'use client';

import { createContext, useContext } from 'react';

import type { SnackbarApi } from './interface';

export const SnackbarContext = createContext<SnackbarApi | null>(null);

// phase-8 task-05: any client component under <Providers> can call
// `useSnackbar().success('Saved')` — docs/FRONTEND-CONVENTIONS.md §9's "friendly snackbar".
export function useSnackbar(): SnackbarApi {
  const api = useContext(SnackbarContext);
  if (api === null) {
    throw new Error('useSnackbar must be used inside <SnackbarProvider>');
  }
  return api;
}
