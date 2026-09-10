import MuiDialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';

import { Button } from '../Button';
import { ErrorState } from '../ErrorState';
import type { ConfirmDialogProps } from './interface';

export default function Component({
  open,
  title,
  body,
  confirmLabel,
  onConfirm,
  onClose,
  isPending,
  errorMessage,
  destructive,
}: ConfirmDialogProps) {
  return (
    <MuiDialog open={open} onClose={onClose}>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <DialogContentText>{body}</DialogContentText>
        {/* fix round 1, F2: reuse ErrorState (role="alert", §9-friendly copy) inside the
            dialog body instead of a silent bare-catch failure. */}
        {errorMessage ? <ErrorState message={errorMessage} /> : null}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={isPending}>
          Cancel
        </Button>
        <Button
          onClick={onConfirm}
          disabled={isPending}
          color={destructive ? 'error' : 'primary'}
          variant="contained"
        >
          {confirmLabel}
        </Button>
      </DialogActions>
    </MuiDialog>
  );
}
