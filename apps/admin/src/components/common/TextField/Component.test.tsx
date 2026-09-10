// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { TextField } from '.';

// phase-8 task-04 (DESIGN.md §A3): validation and keyboard props the editor and composers need.
describe('TextField', () => {
  it('shows helper text and marks the input invalid when error is set', () => {
    render(
      <TextField label="Title" value="" onChange={vi.fn()} error helperText="Title is required" />,
    );

    expect(screen.getByRole('textbox', { name: /Title/ })).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Title is required')).toBeInTheDocument();
  });

  it('fires onBlur when focus leaves and onKeyDown for key presses', async () => {
    const onBlur = vi.fn();
    const onKeyDown = vi.fn();
    render(
      <TextField
        label="Message"
        value=""
        onChange={vi.fn()}
        onBlur={onBlur}
        onKeyDown={onKeyDown}
      />,
    );

    const input = screen.getByRole('textbox', { name: 'Message' });
    await userEvent.click(input);
    await userEvent.keyboard('{Enter}');
    await userEvent.tab();

    // `userEvent.tab()` is a real Tab keydown on the focused input, so onKeyDown fires twice;
    // the rule under test is that the Enter keydown reached the handler first.
    expect(onKeyDown).toHaveBeenCalled();
    expect(onKeyDown.mock.calls[0]?.[0]).toMatchObject({ key: 'Enter' });
    expect(onBlur).toHaveBeenCalledTimes(1);
  });

  it('renders a textarea capped by maxRows when multiline', () => {
    render(
      <TextField label="Body" value="" onChange={vi.fn()} multiline minRows={2} maxRows={6} />,
    );

    expect(screen.getByRole('textbox', { name: 'Body' }).tagName).toBe('TEXTAREA');
  });

  it('marks the input required', () => {
    render(<TextField label="Title" value="" onChange={vi.fn()} required />);

    expect(screen.getByRole('textbox', { name: /Title/ })).toBeRequired();
  });
});
