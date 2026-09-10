import type { ReactNode } from 'react';
export interface SnackbarApi {
  success: (message: string) => void;
  error: (message: string) => void;
}
export interface SnackbarProviderProps {
  children: ReactNode;
}
