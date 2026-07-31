// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { AppSnackbar } from '.';

// task-06 Interfaces: `common/AppSnackbar` surfaces the PRD §9 envelope's `message` for any
// failed mutation (this task's ContentEditorScreen) and is reused as-is by the phase-5 agent
// panel — so its props contract is defined HERE, by this test file, as the frozen contract
// every future caller must match:
//
//   AppSnackbarProps {
//     open: boolean;
//     message: string | null;
//     severity?: 'error' | 'success' | 'info' | 'warning'; // default 'error'
//     onClose: () => void;
//   }
//
// Severity maps to an ARIA live-region role (docs/FRONTEND-CONVENTIONS.md §9 — friendly
// snackbar/notice, never a raw error body): 'error'/'warning' -> role="alert" (assertive —
// matches common/ErrorState's own role); 'success'/'info' -> role="status" (polite — matches
// common/EmptyState's own role). This mirrors MUI's `Alert` component, whose own default is
// `role="alert"` regardless of severity, plus an explicit override for the two polite
// severities. The visible dismiss control is MUI `Alert`'s own default close button (rendered
// whenever `onClose` is passed to `Alert`, accessible name "Close").
//
// `AppSnackbar` does not exist yet — every test below is RED until the implementer creates it
// (task-06 Step 3/4).
describe('AppSnackbar', () => {
  it('severity="error" (the default) renders the message inside a role=alert region', async () => {
    render(<AppSnackbar open message="Could not save due to a conflict." onClose={vi.fn()} />);

    const alert = await screen.findByRole('alert');
    expect(alert).toBeVisible();
    expect(alert).toHaveTextContent('Could not save due to a conflict.');
  });

  it('severity="success" renders the message inside a role=status region, not role=alert', async () => {
    render(<AppSnackbar open message="Saved." severity="success" onClose={vi.fn()} />);

    const status = await screen.findByRole('status');
    expect(status).toHaveTextContent('Saved.');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('open=false renders nothing — no alert/status role and no message text in the document', () => {
    render(<AppSnackbar open={false} message="Hidden message." onClose={vi.fn()} />);

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.queryByText('Hidden message.')).not.toBeInTheDocument();
  });

  it('message=null renders nothing even when open=true', () => {
    render(<AppSnackbar open message={null} onClose={vi.fn()} />);

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('activating the close control calls onClose', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<AppSnackbar open message="Could not save." onClose={onClose} />);

    const closeButton = await screen.findByRole('button', { name: /close/i });
    await user.click(closeButton);

    expect(onClose).toHaveBeenCalled();
  });
});
