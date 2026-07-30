import MuiAlert from '@mui/material/Alert';
import MuiSnackbar from '@mui/material/Snackbar';

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

  return (
    <MuiSnackbar
      open
      onClose={onClose}
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
