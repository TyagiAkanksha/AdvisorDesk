// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { AppSnackbar } from '.';

// fix round 1, M2 (folded, controller-approved — this props contract freezes for phase-5):
// MuiSnackbar forwards ANY click outside itself to `onClose` with `reason: 'clickaway'` — so an
// admin clicking back into the form to fix a save error was silently dismissing the very alert
// telling them what went wrong. The wrapper now swallows only that reason internally; the
// public `{onClose: () => void}` contract (pinned by Component.test.tsx) is unchanged, and an
// explicit close still calls it.
describe('AppSnackbar clickaway handling', () => {
  it('a clickaway (clicking outside the snackbar) does NOT call onClose', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <div>
        <button type="button">Elsewhere on the page</button>
        <AppSnackbar open message="Could not save due to a conflict." onClose={onClose} />
      </div>,
    );

    await screen.findByRole('alert');
    await user.click(screen.getByRole('button', { name: /elsewhere on the page/i }));

    expect(onClose).not.toHaveBeenCalled();
  });

  it('an explicit close (the Alert close button) still calls onClose', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<AppSnackbar open message="Could not save due to a conflict." onClose={onClose} />);

    const closeButton = await screen.findByRole('button', { name: /close/i });
    await user.click(closeButton);

    expect(onClose).toHaveBeenCalled();
  });
});
