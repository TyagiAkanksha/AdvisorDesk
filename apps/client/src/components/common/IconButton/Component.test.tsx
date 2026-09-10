// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { IconButton } from '.';

// phase-8 task-06: icon-only actions (send, stop, menu) get their accessible name on the button.
describe('IconButton', () => {
  it('renders a button named by label that calls onClick', async () => {
    const onClick = vi.fn();
    render(<IconButton name="Search" label="Search" onClick={onClick} />);

    await userEvent.click(screen.getByRole('button', { name: 'Search' }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('can be a submit button and can be disabled', () => {
    render(<IconButton name="Search" label="Send" type="submit" disabled />);

    const button = screen.getByRole('button', { name: 'Send' });
    expect(button).toHaveAttribute('type', 'submit');
    expect(button).toBeDisabled();
  });
});
