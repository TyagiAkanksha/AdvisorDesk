// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ChatWelcome } from '.';

describe('ChatWelcome', () => {
  // p8 t24 (DESIGN.md §B4 carry-in): the page h1 now lives in `ChatScreen` (persists across a
  // conversation) — the welcome region itself renders no heading of its own.
  it('renders a labelled region with no heading, the description, and four suggested-question buttons that send on click', async () => {
    const onAsk = vi.fn();
    render(<ChatWelcome onAsk={onAsk} />);

    expect(screen.getByRole('region', { name: 'Suggested questions' })).toBeInTheDocument();
    // t24 M3: the region must NOT reuse the page heading's name.
    expect(screen.queryByRole('region', { name: 'Ask a question' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading')).not.toBeInTheDocument();
    expect(screen.getByText(/cite their sources/)).toBeInTheDocument();
    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(4);
    await userEvent.click(buttons[0]!);
    expect(onAsk).toHaveBeenCalledWith('When can I withdraw from a Roth IRA without penalty?');
  });
});
