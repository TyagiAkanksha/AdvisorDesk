// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import Providers from '@/app/providers';

import { SnackbarProvider, useSnackbar } from '.';

function Consumer() {
  const snackbar = useSnackbar();
  return (
    <>
      <button type="button" onClick={() => snackbar.success('Saved')}>
        ok
      </button>
      <button type="button" onClick={() => snackbar.error('Could not save')}>
        fail
      </button>
    </>
  );
}

describe('SnackbarProvider / useSnackbar', () => {
  it('shows a polite success notice and an assertive error notice', async () => {
    render(
      <SnackbarProvider>
        <Consumer />
      </SnackbarProvider>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'ok' }));
    expect(screen.getByRole('status')).toHaveTextContent('Saved');

    await userEvent.click(screen.getByRole('button', { name: 'fail' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Could not save');
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('dismisses on the close button but not on a click elsewhere', async () => {
    render(
      <SnackbarProvider>
        <Consumer />
      </SnackbarProvider>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'ok' }));
    await userEvent.click(document.body);
    expect(screen.getByRole('status')).toHaveTextContent('Saved');

    await userEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('throws a clear error when used outside the provider', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    expect(() => render(<Consumer />)).toThrow(
      'useSnackbar must be used inside <SnackbarProvider>',
    );
    consoleError.mockRestore();
  });

  it('is mounted by the app Providers', async () => {
    render(
      <Providers>
        <Consumer />
      </Providers>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'ok' }));
    expect(screen.getByRole('status')).toHaveTextContent('Saved');
  });

  // fix round 1 (Important, plan-mandated): pins the "new notice remounts the Snackbar" rule
  // regardless of timing — two notices must never share a key, even when they land in the same
  // millisecond, or the auto-hide timer would not restart for the second one.
  it('remounts the Snackbar for each new notice, even in rapid succession', async () => {
    render(
      <SnackbarProvider>
        <Consumer />
      </SnackbarProvider>,
    );

    await userEvent.click(screen.getByRole('button', { name: 'ok' }));
    const firstRoot = screen.getByRole('status').closest('.MuiSnackbar-root');

    await userEvent.click(screen.getByRole('button', { name: 'ok' }));
    const secondRoot = screen.getByRole('status').closest('.MuiSnackbar-root');

    expect(secondRoot).not.toBe(firstRoot);
  });
});
