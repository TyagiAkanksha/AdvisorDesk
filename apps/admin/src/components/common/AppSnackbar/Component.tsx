import MuiAlert from '@mui/material/Alert';
import MuiSnackbar from '@mui/material/Snackbar';
import type { SyntheticEvent } from 'react';

import type { AppSnackbarProps } from './interface';

const AUTO_HIDE_DURATION_MS = 6000;

// docs/FRONTEND-CONVENTIONS.md §9: friendly snackbar/notice for a failed mutation's §9
// envelope `message` — never the raw error body. `open=false`/`message=null` render nothing
// at all (no alert/status role, no text) rather than an empty MUI Snackbar shell — the
// explicit "nothing to show" state, decided without depending on MUI's own mount timing.
export default function Component({
  open,
  message,
  severity = 'error',
  onClose,
}: AppSnackbarProps) {
  if (!open || message === null) {
    return null;
  }

  // 'error'/'warning' -> assertive (matches common/ErrorState's role="alert");
  // 'success'/'info' -> polite (matches common/EmptyState's role="status").
  const role = severity === 'error' || severity === 'warning' ? 'alert' : 'status';

  // fix round 1, M2 (folded, controller-approved — this contract freezes for phase-5):
  // MuiSnackbar forwards a click ANYWHERE outside the snackbar to `onClose` as
  // `reason: 'clickaway'` — dismissing a save-failure alert just because the admin clicked
  // back into the form to fix it. Swallow only that reason; the public `{onClose: () => void}`
  // contract (frozen by the pinned Component.test.tsx) is unchanged — an explicit close (the
  // Alert's own close button) or the auto-hide timeout still calls it.
  const handleSnackbarClose = (_event: SyntheticEvent | Event, reason: string) => {
    if (reason === 'clickaway') {
      return;
    }
    onClose();
  };

  return (
    <MuiSnackbar
      open
      onClose={handleSnackbarClose}
      autoHideDuration={AUTO_HIDE_DURATION_MS}
      anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
    >
      <MuiAlert
        severity={severity}
        onClose={onClose}
        role={role}
        variant="filled"
        sx={{ width: '100%' }}
      >
        {message}
      </MuiAlert>
    </MuiSnackbar>
  );
}
