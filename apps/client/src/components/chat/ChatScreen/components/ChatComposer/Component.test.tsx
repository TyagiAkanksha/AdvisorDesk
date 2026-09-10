// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ChatComposer } from '.';

const base = {
  draft: '',
  onDraftChange: vi.fn(),
  onSubmit: vi.fn(),
  onKeyDown: vi.fn(),
  canSend: false,
  streaming: false,
  onStop: vi.fn(),
  onNewConversation: vi.fn(),
  showNewConversation: false,
};

describe('ChatComposer', () => {
  it('renders a multiline Message field, a disabled Send button when nothing can be sent, and the helper line', () => {
    render(<ChatComposer {...base} />);

    expect(screen.getByRole('textbox', { name: 'Message' }).tagName).toBe('TEXTAREA');
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
    expect(screen.getByText(/not financial advice/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'New conversation' })).toBeNull();
  });

  it('submits through the form when Send is enabled and clicked', async () => {
    const onSubmit = vi.fn();
    render(<ChatComposer {...base} draft="Q" canSend onSubmit={onSubmit} />);

    await userEvent.click(screen.getByRole('button', { name: 'Send' }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('swaps Send for Stop while streaming, disables the field, and calls onStop', async () => {
    const onStop = vi.fn();
    render(<ChatComposer {...base} streaming onStop={onStop} />);

    expect(screen.queryByRole('button', { name: 'Send' })).toBeNull();
    expect(screen.getByRole('textbox', { name: 'Message' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Stop' }));
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it('offers New conversation when there are messages', async () => {
    const onNewConversation = vi.fn();
    render(<ChatComposer {...base} showNewConversation onNewConversation={onNewConversation} />);

    await userEvent.click(screen.getByRole('button', { name: 'New conversation' }));
    expect(onNewConversation).toHaveBeenCalledTimes(1);
  });
});
