// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ChatWelcome } from '.';

describe('ChatWelcome', () => {
  it('renders the h1, the description, and four suggested-question buttons that send on click', async () => {
    const onAsk = vi.fn();
    render(<ChatWelcome onAsk={onAsk} />);

    expect(screen.getByRole('heading', { level: 1, name: 'Ask a question' })).toBeInTheDocument();
    expect(screen.getByText(/cite their sources/)).toBeInTheDocument();
    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(4);
    await userEvent.click(buttons[0]!);
    expect(onAsk).toHaveBeenCalledWith('When can I withdraw from a Roth IRA without penalty?');
  });
});
