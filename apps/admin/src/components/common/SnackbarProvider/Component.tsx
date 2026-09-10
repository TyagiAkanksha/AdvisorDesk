'use client';

import MuiAlert from '@mui/material/Alert';
import MuiSnackbar from '@mui/material/Snackbar';
import { useCallback, useMemo, useState } from 'react';
import type { SyntheticEvent } from 'react';

import { SnackbarContext } from './context';
import type { SnackbarApi, SnackbarProviderProps } from './interface';

const SUCCESS_AUTO_HIDE_MS = 4000;
const ERROR_AUTO_HIDE_MS = 8000;

interface Notice {
  key: number;
  severity: 'success' | 'error';
  message: string;
}

// phase-8 task-05 (DESIGN.md §A3): ONE snackbar for the whole admin app, driven through context,
// replacing the per-screen `AppSnackbar` state. Rules carried over from AppSnackbar: a click
// elsewhere on the page ('clickaway') never dismisses a notice — only the close button or the
// timeout; 'error' is an assertive live region (role="alert"), 'success' a polite one
// (role="status"). A new notice replaces the current one (new `key` remounts the Snackbar so
// its timer restarts).
export default function Component({ children }: SnackbarProviderProps) {
  const [notice, setNotice] = useState<Notice | null>(null);

  const notify = useCallback((severity: Notice['severity'], message: string) => {
    setNotice({ key: Date.now(), severity, message });
  }, []);

  const api = useMemo<SnackbarApi>(
    () => ({
      success: (message) => notify('success', message),
      error: (message) => notify('error', message),
    }),
    [notify],
  );

  const handleSnackbarClose = (_event: SyntheticEvent | Event, reason: string) => {
    if (reason === 'clickaway') {
      return;
    }
    setNotice(null);
  };

  return (
    <SnackbarContext.Provider value={api}>
      {children}
      {notice ? (
        <MuiSnackbar
          key={notice.key}
          open
          onClose={handleSnackbarClose}
          autoHideDuration={notice.severity === 'error' ? ERROR_AUTO_HIDE_MS : SUCCESS_AUTO_HIDE_MS}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        >
          <MuiAlert
            severity={notice.severity}
            role={notice.severity === 'error' ? 'alert' : 'status'}
            onClose={() => setNotice(null)}
            variant="filled"
            sx={{ width: '100%' }}
          >
            {notice.message}
          </MuiAlert>
        </MuiSnackbar>
      ) : null}
    </SnackbarContext.Provider>
  );
}
