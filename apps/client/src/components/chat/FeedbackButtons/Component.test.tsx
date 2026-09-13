// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { FeedbackButtons } from '.';

// phase-9 task-17 (DESIGN §A/D2). Dumb leaf: it renders the current rating and raises a choice.
// Queried by accessible name + `aria-pressed`, the two things a screen-reader user actually gets.

describe('FeedbackButtons', () => {
  it('renders both thumbs unpressed when nothing has been rated', () => {
    render(<FeedbackButtons value={null} onSelect={vi.fn()} />);

    expect(screen.getByRole('button', { name: 'Helpful', pressed: false })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Not helpful', pressed: false })).toBeInTheDocument();
  });

  it('reports 1 when the reader clicks thumbs up', async () => {
    const onSelect = vi.fn();
    render(<FeedbackButtons value={null} onSelect={onSelect} />);

    await userEvent.click(screen.getByRole('button', { name: 'Helpful' }));

    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it('reports -1 when the reader clicks thumbs down', async () => {
    const onSelect = vi.fn();
    render(<FeedbackButtons value={null} onSelect={onSelect} />);

    await userEvent.click(screen.getByRole('button', { name: 'Not helpful' }));

    expect(onSelect).toHaveBeenCalledWith(-1);
  });

  it('marks only the chosen thumb as pressed', () => {
    render(<FeedbackButtons value={-1} onSelect={vi.fn()} />);

    expect(screen.getByRole('button', { name: 'Not helpful' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByRole('button', { name: 'Helpful' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });

  it('disables both thumbs while a request is in flight', () => {
    const onSelect = vi.fn();
    render(<FeedbackButtons value={null} disabled onSelect={onSelect} />);

    expect(screen.getByRole('button', { name: 'Helpful' })).toBeDisabled();
    // `fireEvent` (not `user-event`): a real mouse can't land on a `pointer-events: none` disabled
    // MUI button either, but that's a `user-event` simulation guard, not this assertion's concern
    // — MUI's own `ButtonBase` already refuses to invoke `onClick` while `disabled` regardless of
    // how the click event arrives, which is exactly what this test pins.
    fireEvent.click(screen.getByRole('button', { name: 'Not helpful' }));

    expect(onSelect).not.toHaveBeenCalled();
  });
});
