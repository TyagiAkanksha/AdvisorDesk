// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// task-04 / PRD §5.1: the sign-in button is a REAL anchor navigation to the
// backend's `GET /api/v1/auth/login` redirect (Google OAuth consent) — not a
// JS `onClick` handler. `NEXT_PUBLIC_API_URL` drives the href, so it must be
// set BEFORE the component module (and anything it imports) evaluates.
// Static top-level `import` declarations are hoisted ahead of any same-file
// `process.env` assignment in ESM, so stub the env var first, then dynamically
// import the barrel inside each test to guarantee ordering.
const API_URL = 'http://localhost:8000';

describe('SignInScreen', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubEnv('NEXT_PUBLIC_API_URL', API_URL);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it('renders a "Sign in with Google" link whose href is $NEXT_PUBLIC_API_URL/api/v1/auth/login', async () => {
    const { SignInScreen } = await import('.');
    render(<SignInScreen />);

    const link = screen.getByRole('link', { name: /sign in with google/i });

    expect(link).toHaveAttribute('href', `${API_URL}/api/v1/auth/login`);
  });

  it('drives navigation via the anchor href, not an onClick-triggered fetch', async () => {
    const fetchMock = vi.fn();
    global.fetch = fetchMock;
    const user = userEvent.setup();

    const { SignInScreen } = await import('.');
    render(<SignInScreen />);

    const link = screen.getByRole('link', { name: /sign in with google/i });
    expect(link.tagName).toBe('A');

    await user.click(link);

    // A real anchor click never calls fetch itself — the browser follows the
    // href. If the implementation instead wired an onClick handler that
    // fetches the login URL, this would fail.
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
