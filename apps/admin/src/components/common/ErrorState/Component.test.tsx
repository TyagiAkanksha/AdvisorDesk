// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ErrorState } from '.';

// phase-8 task-04: an error state can offer a way out (DESIGN.md §A3 "ErrorState (+action)").
describe('ErrorState', () => {
  it('renders the message in an assertive live region with no button by default', () => {
    render(<ErrorState message="Could not load content." />);

    expect(screen.getByRole('alert')).toHaveTextContent('Could not load content.');
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('renders an action button inside the alert and calls it on click', async () => {
    const onClick = vi.fn();
    render(<ErrorState message="Could not load content." action={{ label: 'Retry', onClick }} />);

    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
