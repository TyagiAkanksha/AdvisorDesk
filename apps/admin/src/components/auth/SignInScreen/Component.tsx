import { Button } from '@/components/common';
import { API_BASE_URL } from '@/lib/apiBase';

// task-04 / PRD §5.1: sign-in is a real anchor navigation to the backend's
// Google OAuth redirect — never a JS-driven fetch. Passing `href` to the
// common Button (MUI's own ButtonBase behavior) renders a plain `<a>`.
//
// `API_BASE_URL` (not a raw `process.env.NEXT_PUBLIC_API_URL` read) so a
// misconfigured production build fails loudly at build time instead of
// shipping an `href="undefined/api/v1/auth/login"` anchor (review round 1,
// I2).
export default function Component() {
  return (
    <Button variant="contained" href={`${API_BASE_URL}/api/v1/auth/login`}>
      Sign in with Google
    </Button>
  );
}
