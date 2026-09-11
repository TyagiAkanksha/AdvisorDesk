import { SIGN_IN_ERROR_FORBIDDEN, SIGN_IN_ERROR_STATE } from './copy';

// phase-8 task-16 (DESIGN.md §C2): maps the `?error=` reason task 13's API callback redirect
// carries to a friendly message. Anything not on this allowlist (missing, unknown, or
// attacker-controlled) renders nothing — the raw query value is never echoed back to the page.
export function signInErrorMessage(reason: string | undefined): string | null {
  switch (reason) {
    case 'forbidden':
      return SIGN_IN_ERROR_FORBIDDEN;
    case 'state':
      return SIGN_IN_ERROR_STATE;
    default:
      return null;
  }
}
