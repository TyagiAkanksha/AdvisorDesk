// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import type { KeyboardEvent } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { TextField } from '.';

// phase-8 task-06: the chat composer needs a growing multiline field and raw key events.
describe('TextField', () => {
  it('renders a textarea when multiline', () => {
    render(
      <TextField label="Message" value="" onChange={vi.fn()} multiline minRows={1} maxRows={6} />,
    );

    expect(screen.getByRole('textbox', { name: 'Message' }).tagName).toBe('TEXTAREA');
  });

  it('forwards key events through onKeyDown', async () => {
    const onKeyDown = vi.fn();
    render(<TextField label="Message" value="" onChange={vi.fn()} onKeyDown={onKeyDown} />);

    await userEvent.click(screen.getByRole('textbox', { name: 'Message' }));
    await userEvent.keyboard('{Enter}');

    expect(onKeyDown).toHaveBeenCalledTimes(1);
    expect(onKeyDown.mock.calls[0]?.[0]).toMatchObject({ key: 'Enter' });
  });

  // p8 t24: type-level pin for the interface change (typed `onKeyDown`, no cast needed by
  // callers). This compiles today too — it is a regression guard, not a RED case.
  it('types onKeyDown as a plain HTMLElement keyboard event (no cast needed by callers)', async () => {
    const seen: string[] = [];
    const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
      seen.push(event.key);
    };
    render(<TextField label="Message" value="" onChange={vi.fn()} onKeyDown={onKeyDown} />);
    await userEvent.type(screen.getByRole('textbox', { name: 'Message' }), 'a');
    expect(seen).toContain('a');
  });
});
