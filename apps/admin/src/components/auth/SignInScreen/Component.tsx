import { Button } from '@/components/common';

// task-04 / PRD §5.1: sign-in is a real anchor navigation to the backend's
// Google OAuth redirect — never a JS-driven fetch. Passing `href` to the
// common Button (MUI's own ButtonBase behavior) renders a plain `<a>`.
export default function Component() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;

  return (
    <Button variant="contained" href={`${apiUrl}/api/v1/auth/login`}>
      Sign in with Google
    </Button>
  );
}
