import { Alert, Box, Button, Paper, Stack, Typography } from '@/components/common';
import { API_BASE_URL } from '@/lib/apiBase';
import { APP_NAME, SIGN_IN_BUTTON_LABEL, SIGN_IN_FINE_PRINT, SIGN_IN_SUBTITLE } from '@/lib/copy';
import { signInErrorMessage } from '@/lib/signInError';

import type { SignInScreenProps } from './interface';

// task-04 / PRD §5.1: sign-in is a real anchor navigation to the backend's
// Google OAuth redirect — never a JS-driven fetch. Passing `href` to the
// common Button (MUI's own ButtonBase behavior) renders a plain `<a>`.
//
// `API_BASE_URL` (not a raw `process.env.NEXT_PUBLIC_API_URL` read) so a
// misconfigured production build fails loudly at build time instead of
// shipping an `href="undefined/api/v1/auth/login"` anchor (review round 1,
// I2).
//
// phase-8 task-16 (DESIGN.md §C2): the bare button is now a centred outlined
// card (wordmark, subtitle, button, fine print) plus an optional `?error=`
// message. `error` is a plain prop (not `useSearchParams()`) so this stays a
// Server Component with no hooks and no Suspense boundary.
export default function Component({ error }: SignInScreenProps) {
  const message = signInErrorMessage(error);

  return (
    <Box
      component="main"
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        p: 2,
      }}
    >
      <Paper variant="outlined" sx={{ p: 4, width: '100%', maxWidth: 400 }}>
        <Stack spacing={2}>
          <Typography variant="h3" component="h1">
            {APP_NAME}
          </Typography>
          <Typography variant="body1" color="text.secondary">
            {SIGN_IN_SUBTITLE}
          </Typography>
          {message ? <Alert severity="error">{message}</Alert> : null}
          <Button variant="contained" href={`${API_BASE_URL}/api/v1/auth/login`} fullWidth>
            {SIGN_IN_BUTTON_LABEL}
          </Button>
          <Typography variant="caption" color="text.secondary" component="p">
            {SIGN_IN_FINE_PRINT}
          </Typography>
        </Stack>
      </Paper>
    </Box>
  );
}
